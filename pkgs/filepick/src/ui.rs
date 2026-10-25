include!(env!("DOTFILES_THEME_RS"));
use crate::{search::Search, transfer};
use anyhow::Result;
use crossterm::{
    event::{
        self, DisableBracketedPaste, EnableBracketedPaste, Event, KeyCode, KeyEvent, KeyEventKind,
        KeyModifiers,
    },
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use nucleo::pattern::{CaseMatching, Normalization};
use ratatui::{
    backend::CrosstermBackend,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph, Wrap},
    Frame, Terminal,
};
use std::{collections::BTreeSet, io, path::PathBuf, sync::atomic::Ordering, time::Duration};

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Action {
    Attach,
    Copy,
    Drag,
    Paths,
}

struct Visual {
    anchor: u32,
    base: BTreeSet<PathBuf>,
}

struct App {
    search: Search,
    root: PathBuf,
    all: bool,
    personal: bool,
    query: String,
    insert: bool,
    cursor: u32,
    offset: u32,
    height: u32,
    selected: BTreeSet<PathBuf>,
    visual: Option<Visual>,
    pending_g: bool,
    help: bool,
    preview_path: Option<PathBuf>,
    preview: String,
}

impl App {
    fn new(root: PathBuf, all: bool, query: String, personal: bool, refresh: bool) -> Self {
        let search = Search::new(root.clone(), all, personal, refresh);
        let mut app = Self {
            search,
            root,
            all,
            personal,
            query,
            insert: true,
            cursor: 0,
            offset: 0,
            height: 20,
            selected: BTreeSet::new(),
            visual: None,
            pending_g: false,
            help: false,
            preview_path: None,
            preview: String::new(),
        };
        app.reparse();
        app
    }

    fn reparse(&mut self) {
        self.visual = None;
        self.cursor = 0;
        self.offset = 0;
        self.search.matcher.pattern.reparse(
            0,
            &self.query,
            CaseMatching::Smart,
            Normalization::Smart,
            false,
        );
    }

    fn count(&self) -> u32 {
        self.search.matcher.snapshot().matched_item_count()
    }

    fn current(&self) -> Option<PathBuf> {
        self.search
            .matcher
            .snapshot()
            .get_matched_item(self.cursor)
            .map(|item| item.data.path.clone())
    }

    fn files(&self) -> Vec<PathBuf> {
        if self.selected.is_empty() {
            self.current().into_iter().collect()
        } else {
            self.selected.iter().cloned().collect()
        }
    }

    fn move_to(&mut self, cursor: u32) {
        self.cursor = cursor.min(self.count().saturating_sub(1));
        if let Some(visual) = &self.visual {
            self.selected = visual.base.clone();
            let start = visual.anchor.min(self.cursor);
            let end = (visual.anchor.max(self.cursor) + 1).min(self.count());
            for item in self.search.matcher.snapshot().matched_items(start..end) {
                self.selected.insert(item.data.path.clone());
            }
        }
    }

    fn toggle(&mut self) {
        if self.visual.take().is_some() {
            return;
        }
        if let Some(path) = self.current() {
            if !self.selected.remove(&path) {
                self.selected.insert(path);
            }
        }
    }

    fn refresh(&mut self, force: bool) {
        self.search = Search::new(self.root.clone(), self.all, self.personal, force);
        self.preview_path = None;
        self.reparse();
    }

    fn handle(&mut self, key: KeyEvent) -> Result<Option<Action>> {
        let control = key.modifiers.contains(KeyModifiers::CONTROL);
        if control {
            match key.code {
                KeyCode::Char('n' | 'j') => self.move_to(self.cursor.saturating_add(1)),
                KeyCode::Char('p' | 'k') => self.move_to(self.cursor.saturating_sub(1)),
                KeyCode::Char('d') => self.move_to(self.cursor.saturating_add(self.height / 2)),
                KeyCode::Char('u') if !self.insert => {
                    self.move_to(self.cursor.saturating_sub(self.height / 2))
                }
                KeyCode::Char('u') => {
                    self.query.clear();
                    self.reparse();
                }
                KeyCode::Char('w') if self.insert => {
                    self.query = self.query.trim_end().to_owned();
                    while self
                        .query
                        .chars()
                        .last()
                        .is_some_and(|c| !c.is_whitespace())
                    {
                        self.query.pop();
                    }
                    self.reparse();
                }
                KeyCode::Char('a') => {
                    self.visual = None;
                    for item in self.search.matcher.snapshot().matched_items(..) {
                        self.selected.insert(item.data.path.clone());
                    }
                }
                KeyCode::Char('x') => {
                    self.visual = None;
                    self.selected.clear();
                }
                KeyCode::Char('r') => {
                    self.root = if self.root == std::path::Path::new("/") {
                        transfer::home()?
                    } else {
                        PathBuf::from("/")
                    };
                    self.personal = self.root != std::path::Path::new("/");
                    self.refresh(false);
                }
                _ => {}
            }
            return Ok(None);
        }
        if self.help {
            self.help = false;
            return Ok(None);
        }
        match key.code {
            KeyCode::Enter => return Ok(Some(Action::Attach)),
            KeyCode::Esc => {
                self.insert = false;
                self.visual = None;
                self.pending_g = false;
            }
            KeyCode::Tab => {
                self.toggle();
                self.move_to(self.cursor.saturating_add(1));
            }
            KeyCode::BackTab => {
                self.toggle();
                self.move_to(self.cursor.saturating_sub(1));
            }
            KeyCode::Down => self.move_to(self.cursor.saturating_add(1)),
            KeyCode::Up => self.move_to(self.cursor.saturating_sub(1)),
            KeyCode::PageDown => self.move_to(self.cursor.saturating_add(self.height)),
            KeyCode::PageUp => self.move_to(self.cursor.saturating_sub(self.height)),
            KeyCode::Home if !self.insert => self.move_to(0),
            KeyCode::End if !self.insert => self.move_to(self.count().saturating_sub(1)),
            KeyCode::Backspace if self.insert => {
                self.query.pop();
                self.reparse();
            }
            KeyCode::Char(c) if self.insert => {
                self.query.push(c);
                self.reparse();
            }
            KeyCode::Char(c) => {
                let gg = self.pending_g && c == 'g';
                self.pending_g = false;
                match c {
                    'j' => self.move_to(self.cursor.saturating_add(1)),
                    'k' => self.move_to(self.cursor.saturating_sub(1)),
                    'g' if gg => self.move_to(0),
                    'g' => self.pending_g = true,
                    'G' => self.move_to(self.count().saturating_sub(1)),
                    ' ' => self.toggle(),
                    'v' | 'V' => {
                        if self.visual.take().is_none() && self.count() > 0 {
                            self.visual = Some(Visual {
                                anchor: self.cursor,
                                base: self.selected.clone(),
                            });
                            self.move_to(self.cursor);
                        }
                    }
                    'a' => {
                        self.visual = None;
                        for item in self.search.matcher.snapshot().matched_items(..) {
                            self.selected.insert(item.data.path.clone());
                        }
                    }
                    'x' => {
                        self.visual = None;
                        self.selected.clear();
                    }
                    '/' => {
                        self.query.clear();
                        self.insert = true;
                        self.reparse();
                    }
                    'i' => {
                        self.insert = true;
                        self.visual = None;
                    }
                    'y' => return Ok(Some(Action::Copy)),
                    'd' => return Ok(Some(Action::Drag)),
                    'Y' => return Ok(Some(Action::Paths)),
                    'r' => self.refresh(true),
                    '.' => {
                        self.all = !self.all;
                        self.refresh(false);
                    }
                    '?' => self.help = true,
                    _ => {}
                }
            }
            _ => {}
        }
        Ok(None)
    }

    fn draw(&mut self, frame: &mut Frame) {
        let palette = desktop_theme::palette();
        let [r,g,b] = palette.accent;
        let accent = Color::Rgb(r,g,b);
        let [r,g,b] = palette.muted;
        let muted = Color::Rgb(r,g,b);
        let [r,g,b] = palette.surface;
        let surface = Color::Rgb(r,g,b);
        let areas = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Length(2),
                Constraint::Length(3),
                Constraint::Min(1),
                Constraint::Length(3),
            ])
            .split(frame.area());
        let scanning = if self.search.rebuilding.load(Ordering::Acquire) {
            " · cached · updating…"
        } else if self.search.cached.load(Ordering::Acquire) {
            if self.search.done.load(Ordering::Acquire) {
                " · cached"
            } else {
                " · cached · checking folders…"
            }
        } else if self.search.done.load(Ordering::Acquire) {
            " · indexed"
        } else {
            " · scanning…"
        };
        let mode = if self.insert {
            "SEARCH"
        } else if self.visual.is_some() {
            "VISUAL"
        } else {
            "NORMAL"
        };
        frame.render_widget(
            Paragraph::new(vec![
                Line::from(vec![
                    Span::styled(
                        " FILEPICK ",
                        Style::default().fg(accent).add_modifier(Modifier::BOLD),
                    ),
                    Span::raw(format!(" {mode} · {} selected", self.selected.len())),
                ]),
                Line::styled(
                    format!(
                        " {} · {} matches / {} files{scanning} · {} unreadable · {}",
                        transfer::clean(&self.root.display().to_string()),
                        self.count(),
                        self.search.matcher.snapshot().item_count(),
                        self.search.errors.load(Ordering::Relaxed),
                        if self.all {
                            "all files"
                        } else if self.personal {
                            "personal files"
                        } else {
                            "useful files"
                        }
                    ),
                    Style::default().fg(muted),
                ),
            ]),
            areas[0],
        );
        frame.render_widget(
            Paragraph::new(format!(
                "/ {}{}",
                transfer::clean(&self.query),
                if self.insert { "▏" } else { "" }
            ))
            .block(
                Block::default()
                    .borders(Borders::ALL)
                    .border_style(Style::default().fg(accent))
                    .title(" Fuzzy search · Esc for Vim keys "),
            ),
            areas[1],
        );
        let panes = Layout::default()
            .direction(Direction::Horizontal)
            .constraints(if frame.area().width >= 100 {
                vec![Constraint::Percentage(60), Constraint::Percentage(40)]
            } else {
                vec![Constraint::Percentage(100), Constraint::Length(0)]
            })
            .split(areas[2]);
        self.height = u32::from(panes[0].height.saturating_sub(2)).max(1);
        self.cursor = self.cursor.min(self.count().saturating_sub(1));
        if self.cursor < self.offset {
            self.offset = self.cursor;
        }
        if self.cursor >= self.offset + self.height {
            self.offset = self.cursor + 1 - self.height;
        }
        let mut lines = Vec::new();
        let end = (self.offset + self.height).min(self.count());
        for index in self.offset.min(end)..end {
            if let Some(item) = self.search.matcher.snapshot().get_matched_item(index) {
                let marked = self.selected.contains(&item.data.path);
                let mut style = Style::default();
                if marked {
                    style = style.fg(accent);
                }
                if index == self.cursor {
                    style = style
                        .bg(surface)
                        .add_modifier(Modifier::BOLD);
                }
                lines.push(Line::styled(
                    format!(
                        "{} {} {}",
                        if index == self.cursor { "›" } else { " " },
                        if marked { "●" } else { "○" },
                        transfer::clean(&item.data.label)
                    ),
                    style,
                ));
            }
        }
        if lines.is_empty() {
            lines.push(Line::styled(
                " No matches. Change the search, or Ctrl+R to change scope.",
                Style::default().fg(muted),
            ));
        }
        frame.render_widget(
            Paragraph::new(lines).block(Block::default().borders(Borders::ALL).title(" Files ")),
            panes[0],
        );
        if panes[1].width > 0 {
            self.draw_details(frame, panes[1], accent);
        }
        let footer = if self.insert {
            " Type to search · Tab select · Ctrl+J/K move · Enter attach to Firefox / copy · Esc Vim mode\n Ctrl+A select matches · Ctrl+X clear selection · Ctrl+R personal/system · Ctrl+C quit"
        } else {
            " j/k move · Space/Tab select · v range · / new search · i edit · Enter attach/copy · y copy · d drag · Y paths\n gg/G first/last · Ctrl+D/U page · a select matches · x clear · . all files · r rebuild · Ctrl+R personal/system · ? help · q quit"
        };
        frame.render_widget(
            Paragraph::new(footer).style(Style::default().fg(muted)),
            areas[3],
        );
        if self.help {
            frame.render_widget(ratatui::widgets::Clear, areas[2]);
            frame.render_widget(Paragraph::new("Search filenames and paths with fuzzy matching. Space-separated terms must all match.\nUse report .pdf to narrow results; 'report is exact text; !draft excludes a term.\n\nSEARCH: type a query; Tab toggles a file; Ctrl+J/K or arrows move; Esc enters NORMAL.\nNORMAL: j/k move; gg/G first/last; Ctrl+D/U half-page; Space toggles; Tab toggles and moves.\nv starts a VISUAL range; j/k extends or shrinks it; v/Esc keeps the range and leaves VISUAL.\na / Ctrl+A selects all current matches; x / Ctrl+X clears the entire selection.\n/ starts a new search; i edits the current query. Selected files survive searches and scope changes.\n\nEnter: attach ALL selected files to the original Firefox input when opened with Super+Alt+F.\nFirefox receives one paste per file automatically; no drag window or manual paste is needed.\ny: copy ALL selected files without attaching; terminals receive every path as text.\nd: copy and open a drag window. Hold left-click on its file group, drag to the upload box, release.\nY: copy file paths as text, useful for a coding assistant with access to this machine.\nfilepick --drag-last: reopen the drag window for the last copied selection.\n\nDefault: cached personal documents, downloads, media, projects, and dotfiles.\nFolder timestamps are checked in the background; changes rebuild the index automatically.\nCtrl+R switches personal/system. . includes all hidden/ignored/generated files. r forces a rebuild.\nProject .gitignore and .filepick-ignore rules are respected by default.\n/proc /sys /dev /run /nix are skipped during system search.\nPermission errors are counted and skipped. Symlink directories are not followed.\nq or Ctrl+C quits without copying. Any key closes this help.")
                .wrap(Wrap {trim: false}).block(Block::default().borders(Borders::ALL).title(" Filepick help ")), areas[2]);
        }
    }

    fn draw_details(&mut self, frame: &mut Frame, area: Rect, accent: Color) {
        let panes = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Min(3),
                Constraint::Length(self.selected.len().min(7) as u16 + 2),
            ])
            .split(area);
        let current = self.current();
        if current != self.preview_path {
            self.preview = current
                .as_ref()
                .map(|p| transfer::preview(p))
                .unwrap_or_default();
            self.preview_path = current;
        }
        frame.render_widget(
            Paragraph::new(self.preview.as_str())
                .wrap(Wrap { trim: false })
                .block(Block::default().borders(Borders::ALL).title(" Preview ")),
            panes[0],
        );
        let mut lines: Vec<Line> = self
            .selected
            .iter()
            .take(6)
            .map(|p| {
                Line::styled(
                    transfer::clean(&p.display().to_string()),
                    Style::default().fg(accent),
                )
            })
            .collect();
        if self.selected.len() > 6 {
            lines.push(Line::raw(format!("… and {} more", self.selected.len() - 6)));
        }
        frame.render_widget(
            Paragraph::new(lines).block(
                Block::default()
                    .borders(Borders::ALL)
                    .title(format!(" Selected ({}) ", self.selected.len())),
            ),
            panes[1],
        );
    }
}

struct Screen;
impl Drop for Screen {
    fn drop(&mut self) {
        let _ = disable_raw_mode();
        let _ = execute!(io::stderr(), DisableBracketedPaste, LeaveAlternateScreen);
    }
}

pub fn pick(
    root: PathBuf,
    all: bool,
    query: String,
    personal: bool,
    refresh: bool,
) -> Result<Option<(Vec<PathBuf>, Action)>> {
    enable_raw_mode()?;
    let _screen = Screen;
    execute!(io::stderr(), EnterAlternateScreen, EnableBracketedPaste)?;
    let old_hook = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        drop(Screen);
        old_hook(info);
    }));
    let mut terminal = Terminal::new(CrosstermBackend::new(io::stderr()))?;
    let mut app = App::new(root, all, query, personal, refresh);
    let mut dirty = true;
    let mut previous_state = (false, false, false);
    loop {
        let mut matching = false;
        // Freeze result order during a visual range so streaming never changes its contents.
        if app.visual.is_none() {
            let status = app.search.tick(5);
            dirty |= status.changed;
            matching = status.running;
        }
        let state = (
            app.search.done.load(Ordering::Acquire),
            app.search.cached.load(Ordering::Acquire),
            app.search.rebuilding.load(Ordering::Acquire),
        );
        if dirty || state != previous_state {
            terminal.draw(|frame| app.draw(frame))?;
        }
        previous_state = state;
        dirty = false;
        let wait = if matching || !state.0 { 16 } else { 250 };
        if !event::poll(Duration::from_millis(wait))? {
            continue;
        }
        dirty = true;
        match event::read()? {
            Event::Key(key) if key.kind != KeyEventKind::Release => {
                if key.code == KeyCode::Char('c') && key.modifiers.contains(KeyModifiers::CONTROL)
                    || key.code == KeyCode::Char('q') && !app.insert && !app.help
                {
                    return Ok(None);
                }
                if let Some(action) = app.handle(key)? {
                    let files = app.files();
                    if !files.is_empty() {
                        return Ok(Some((files, action)));
                    }
                }
            }
            Event::Paste(text) if app.insert => {
                app.query.push_str(&text);
                app.reparse();
            }
            _ => {}
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::search::Entry;
    use std::{thread, time::Instant};

    fn app() -> App {
        let dir = tempfile::tempdir().unwrap();
        let mut app = App::new(dir.path().to_owned(), false, String::new(), false, false);
        let injector = app.search.matcher.injector();
        for name in ["alpha.txt", "beta.pdf", "gamma.txt", "delta.pdf"] {
            injector.push(
                Entry {
                    path: PathBuf::from(format!("/tmp/{name}")),
                    label: name.into(),
                },
                |e, c| c[0] = e.label.as_str().into(),
            );
        }
        let deadline = Instant::now() + Duration::from_secs(5);
        loop {
            app.search.matcher.tick(10);
            if app.count() == 4 {
                break;
            }
            assert!(Instant::now() < deadline);
            thread::sleep(Duration::from_millis(5));
        }
        app.insert = false;
        app
    }

    fn key(app: &mut App, c: char) {
        app.handle(KeyEvent::new(KeyCode::Char(c), KeyModifiers::NONE))
            .unwrap();
    }

    #[test]
    fn visual_range_expands_and_shrinks_and_preserves_earlier_selection() {
        let mut app = app();
        key(&mut app, ' ');
        key(&mut app, 'j');
        key(&mut app, 'v');
        key(&mut app, 'j');
        assert_eq!(app.selected.len(), 3);
        key(&mut app, 'k');
        assert_eq!(app.selected.len(), 2);
        key(&mut app, 'v');
        assert!(app.visual.is_none());
        assert_eq!(app.selected.len(), 2);
    }

    #[test]
    fn selections_survive_search_changes_and_override_current_file() {
        let mut app = app();
        key(&mut app, ' ');
        let selected = app.files();
        key(&mut app, '/');
        key(&mut app, 'z');
        assert_eq!(app.files(), selected);
        assert!(app.insert);
    }

    #[test]
    fn enter_copies_the_entire_selection_instead_of_the_highlighted_file() {
        let mut app = app();
        key(&mut app, ' ');
        key(&mut app, 'j');
        key(&mut app, ' ');
        key(&mut app, 'j');
        let highlighted = app.current().unwrap();
        let action = app
            .handle(KeyEvent::new(KeyCode::Enter, KeyModifiers::NONE))
            .unwrap();
        assert_eq!(action, Some(Action::Attach));
        let copied = app.files();
        assert_eq!(copied.len(), 2);
        assert!(!copied.contains(&highlighted));
        assert_eq!(copied.into_iter().collect::<BTreeSet<_>>(), app.selected);
    }

    #[test]
    fn vim_keys_require_normal_mode_and_copy_actions_are_distinct() {
        let mut app = app();
        key(&mut app, 'i');
        for c in ['j', 'k', 'd', 'y'] {
            key(&mut app, c);
        }
        assert_eq!(app.query, "jkdy");
        app.handle(KeyEvent::new(KeyCode::Esc, KeyModifiers::NONE))
            .unwrap();
        for (c, action) in [
            ('y', Action::Copy),
            ('d', Action::Drag),
            ('Y', Action::Paths),
        ] {
            assert_eq!(
                app.handle(KeyEvent::new(KeyCode::Char(c), KeyModifiers::NONE))
                    .unwrap(),
                Some(action)
            );
        }
    }

    #[test]
    fn rendering_handles_small_terminals() {
        let mut app = app();
        for (width, height) in [(120, 35), (55, 15), (10, 5), (1, 1)] {
            let mut terminal =
                Terminal::new(ratatui::backend::TestBackend::new(width, height)).unwrap();
            terminal.draw(|frame| app.draw(frame)).unwrap();
        }
    }
}
