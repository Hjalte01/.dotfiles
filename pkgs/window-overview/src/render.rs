include!(env!("DOTFILES_THEME_RS"));
use crate::{
    hypr::Snapshot,
    layout::{self, Card, Group, Rect, Scope, SetPanel},
};
use fast_image_resize as fir;
use fontdue::{Font, FontSettings, Metrics};
use image::{Rgba, RgbaImage};
use serde::Serialize;
use std::collections::HashMap;

pub struct Capture {
    pub width: u32,
    pub height: u32,
    pub pixels: Vec<u8>,
    pub generation: u64,
}
#[derive(Clone, Copy, Debug, Default, PartialEq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum ViewMode {
    #[default]
    Workspaces,
    Windows,
}
impl ViewMode {
    pub fn next(self) -> Self {
        match self {
            Self::Workspaces => Self::Windows,
            Self::Windows => Self::Workspaces,
        }
    }
    pub fn label(self) -> &'static str {
        match self {
            Self::Workspaces => "Workspaces",
            Self::Windows => "Windows",
        }
    }
}
#[derive(Clone, Copy)]
pub enum Browse {
    First,
    Last,
    Previous,
    Next,
}
#[derive(Default)]
pub struct Ui {
    pub snapshot: Option<Snapshot>,
    pub query: String,
    pub workspace: Option<i64>,
    pub mode: ViewMode,
    pub all_sets: bool,
    pub selected: usize,
    pub inspect: bool,
    pub native: bool,
    pub pan: [f32; 2],
    pub numbers_in_search: bool,
    pub groups: Vec<Group>,
    pub set_panels: Vec<SetPanel>,
    pub hits: Vec<(Rect, Action)>,
    pub pointer: [f32; 2],
    pub error: String,
}
impl Ui {
    pub fn browse(&mut self, direction: Browse) {
        let indices = self.indices();
        if indices.is_empty() {
            return;
        }
        let position = indices.iter().position(|&i| i == self.selected);
        let target = match direction {
            Browse::First => 0,
            Browse::Last => indices.len() - 1,
            Browse::Next => position.map_or(0, |p| (p + 1) % indices.len()),
            Browse::Previous => position.map_or(indices.len() - 1, |p| {
                (p + indices.len() - 1) % indices.len()
            }),
        };
        self.selected = indices[target];
        self.pan = [0., 0.];
    }
    pub fn scope(&self) -> Scope {
        Scope {
            workspace: self.workspace,
            all_sets: self.all_sets,
        }
    }
    pub fn indices(&self) -> Vec<usize> {
        self.snapshot
            .as_ref()
            .map(|s| layout::matching(s, &self.query, self.scope()))
            .unwrap_or_default()
    }
}
#[derive(Clone, Debug)]
pub enum Action {
    Select(usize),
    Inspect(usize),
    Workspace(i64),
    All,
    Mode,
    View(ViewMode),
    Scope(bool),
    Back,
    Native,
    Fit,
    Focus,
}

type GlyphCache = HashMap<(char, u32), (Metrics, Vec<u8>)>;
type ImageCache = HashMap<(String, u32, u32, u64), Vec<u8>>;
pub struct Renderer {
    font: Font,
    glyphs: GlyphCache,
    resized: ImageCache,
    resizer: fir::Resizer,
    pub last_render_ms: f64,
}
impl Renderer {
    pub fn new() -> Self {
        Self {
            font: Font::from_bytes(
                include_bytes!(env!("OVERVIEW_FONT")) as &[u8],
                FontSettings::default(),
            )
            .unwrap(),
            glyphs: HashMap::new(),
            resized: HashMap::new(),
            resizer: fir::Resizer::new(),
            last_render_ms: 0.,
        }
    }
    pub fn draw(
        &mut self,
        ui: &mut Ui,
        captures: &HashMap<String, Capture>,
        width: u32,
        height: u32,
        scale: u32,
    ) -> RgbaImage {
        let start = std::time::Instant::now();
        let theme = desktop_theme::palette();
        let mut canvas = Canvas {
            theme: theme.clone(),
            image: RgbaImage::from_pixel(
                width,
                height,
                Rgba([theme.base[0], theme.base[1], theme.base[2], 255]),
            ),
            scale: scale as f32,
            font: &self.font,
            glyphs: &mut self.glyphs,
        };
        let w = width as f32 / scale as f32;
        let h = height as f32 / scale as f32;
        // A quiet tonal backdrop, derived entirely from the current desktop theme.
        for y in 0..height {
            let color = mix(
                theme.base,
                theme.surface,
                0.22 * (1. - y as f32 / height as f32),
            );
            for x in 0..width {
                canvas
                    .image
                    .put_pixel(x, y, Rgba([color[0], color[1], color[2], 255]));
            }
        }
        ui.hits.clear();
        if let Some(snapshot) = &ui.snapshot {
            canvas.text(
                32.,
                22.,
                if ui.inspect {
                    "Window preview"
                } else {
                    ui.mode.label()
                },
                30.,
                theme.text,
                w - 360.,
            );
            let subtitle = format!(
                "{}  ·  {} workspaces  ·  {} windows",
                if ui.all_sets {
                    "All sets"
                } else {
                    snapshot.set_name(&snapshot.current_set)
                },
                snapshot
                    .workspaces
                    .iter()
                    .filter(|w| ui.scope().includes(snapshot, w))
                    .count(),
                ui.indices().len()
            );
            canvas.text(
                33.,
                62.,
                &subtitle,
                14.,
                mix(theme.base, theme.muted, 0.76),
                w - 360.,
            );
            let destination = Rect::new(w - 266., 27., 234., 38.);
            canvas.rounded(destination, mix(theme.base, theme.accent, 0.10), 10.);
            canvas.rounded(
                Rect::new(destination.x + 14., 43., 7., 7.),
                theme.accent,
                3.5,
            );
            canvas.text(
                destination.x + 31.,
                35.,
                &format!("Focus here: {}", snapshot.monitor),
                14.,
                theme.accent,
                190.,
            );
            let mode = Rect::new(w - 320., 96., 288., 44.);
            canvas.rounded(mode, mix(theme.base, theme.surface, 0.7), 12.);
            for (view, offset, width) in [
                (ViewMode::Workspaces, 4., 144.),
                (ViewMode::Windows, 152., 132.),
            ] {
                let active = ui.mode == view;
                let segment = Rect::new(mode.x + offset, mode.y + 4., width, 36.);
                if active {
                    canvas.rounded(segment, mix(theme.surface, theme.accent, 0.19), 9.);
                }
                canvas.centered(
                    segment,
                    view.label(),
                    14.,
                    if active { theme.accent } else { theme.muted },
                );
                ui.hits.push((segment, Action::View(view)));
            }
            let scope = Rect::new(w - 582., 96., 244., 44.);
            canvas.rounded(scope, mix(theme.base, theme.surface, 0.7), 12.);
            for (all, label, offset) in [(false, "Current set", 4.), (true, "All sets", 126.)] {
                let active = all == ui.all_sets;
                let segment = Rect::new(scope.x + offset, scope.y + 4., 114., 36.);
                if active {
                    canvas.rounded(segment, mix(theme.surface, theme.accent, 0.19), 9.);
                }
                canvas.centered(
                    segment,
                    label,
                    13.,
                    if active { theme.accent } else { theme.muted },
                );
                ui.hits.push((segment, Action::Scope(all)));
            }
            if ui.inspect {
                if let Some(c) = snapshot.clients.get(ui.selected) {
                    canvas.text(
                        26.,
                        107.,
                        &format!(
                            "[{}]  {}  ·  {}  ·  {}",
                            ui.selected + 1,
                            c.app(),
                            snapshot.context(&c.workspace),
                            c.states()
                        ),
                        18.,
                        theme.muted,
                        w - 646.,
                    );
                    let area = Rect::new(32., 162., w - 64., h - 233.);
                    canvas.fill(area, theme.base);
                    if let Some(capture) = captures.get(&c.address) {
                        let mut r = area.fit(
                            capture.width as f32 / scale as f32,
                            capture.height as f32 / scale as f32,
                        );
                        if ui.native {
                            // Exactly one capture pixel to one output-buffer pixel.
                            let sw = capture.width as f32 / scale as f32;
                            let sh = capture.height as f32 / scale as f32;
                            ui.pan[0] = ui.pan[0].clamp(0., (sw - area.w).max(0.));
                            ui.pan[1] = ui.pan[1].clamp(0., (sh - area.h).max(0.));
                            r = Rect::new(
                                area.x + (area.w - sw).max(0.) / 2. - ui.pan[0],
                                area.y + (area.h - sh).max(0.) / 2. - ui.pan[1],
                                sw,
                                sh,
                            );
                        }
                        paint_capture(
                            &mut canvas,
                            &mut self.resizer,
                            &mut self.resized,
                            &c.address,
                            capture,
                            r,
                            area,
                            ui.native,
                            0.,
                        );
                    } else {
                        canvas.text(
                            area.x + 20.,
                            area.y + 20.,
                            "Capturing original pixels…",
                            20.,
                            theme.muted,
                            area.w - 40.,
                        );
                    }
                    for (i, (label, action, active)) in [
                        ("100% · Ctrl+1", Action::Native, ui.native),
                        ("Fit · Ctrl+0", Action::Fit, !ui.native),
                        ("Focus · Enter", Action::Focus, false),
                        ("Back · Esc", Action::Back, false),
                    ]
                    .into_iter()
                    .enumerate()
                    {
                        let rect = Rect::new(w - 680. + i as f32 * 164., h - 49., 154., 33.);
                        canvas.button(rect, label, active);
                        ui.hits.push((rect, action));
                    }
                    canvas.text(
                        26.,
                        h - 40.,
                        "Drag / scroll to pan · ← → / PgUp PgDn browse · Home / End",
                        16.,
                        theme.muted,
                        w - 730.,
                    );
                }
            } else {
                let search = if ui.query.is_empty() {
                    if ui.numbers_in_search {
                        "Search (numbers included)…"
                    } else {
                        "Search apps, titles, workspaces or sets…"
                    }
                } else {
                    &ui.query
                };
                let search_rect = Rect::new(32., 96., w - 646., 44.);
                canvas.rounded(search_rect, mix(theme.base, theme.surface, 0.8), 12.);
                canvas.outline(
                    search_rect,
                    if ui.query.is_empty() {
                        theme.overlay
                    } else {
                        theme.accent
                    },
                    12.,
                    1.,
                );
                // Magnifying glass, drawn natively so it matches the theme at any scale.
                canvas.outline(Rect::new(49., 110., 13., 13.), theme.muted, 6.5, 1.5);
                canvas.rounded(Rect::new(60., 121., 6., 2.), theme.muted, 1.);
                canvas.text(
                    79.,
                    107.,
                    search,
                    16.,
                    if ui.query.is_empty() {
                        mix(theme.base, theme.muted, 0.76)
                    } else {
                        theme.text
                    },
                    search_rect.w - 112.,
                );
                let indices = ui.indices();
                if !indices.contains(&ui.selected) {
                    ui.selected = indices.first().copied().unwrap_or(snapshot.clients.len());
                }
                let area = Rect::new(32., 164., w - 64., h - 242.);
                (ui.set_panels, ui.groups) = layout::arrange_overview(
                    snapshot,
                    &indices,
                    area,
                    ui.mode == ViewMode::Windows,
                    ui.scope(),
                );
                for panel in &ui.set_panels {
                    let current = panel.id.as_deref() == Some(snapshot.current_set.as_str());
                    canvas.shadow(panel.rect, 20., 0.12);
                    canvas.rounded(
                        panel.rect,
                        mix(
                            theme.base,
                            theme.accent,
                            if current { 0.075 } else { 0.025 },
                        ),
                        20.,
                    );
                    canvas.outline(
                        panel.rect,
                        mix(
                            theme.overlay,
                            theme.accent,
                            if current { 0.60 } else { 0.10 },
                        ),
                        20.,
                        if current { 2. } else { 1. },
                    );
                    canvas.text(
                        panel.rect.x + 18.,
                        panel.rect.y + 10.,
                        &format!("{}{}", panel.name, if current { " · Current" } else { "" }),
                        19.,
                        if current { theme.accent } else { theme.text },
                        panel.rect.w - 36.,
                    );
                }
                for group in &ui.groups {
                    if ui.mode != ViewMode::Windows {
                        let current = snapshot.monitors.iter().any(|m| {
                            m.name == snapshot.monitor && m.active_workspace.id == group.id
                        });
                        canvas.shadow(group.rect, 18., 0.10);
                        canvas.rounded(group.rect, mix(theme.base, theme.surface, 0.72), 18.);
                        canvas.outline(
                            group.rect,
                            mix(theme.surface, theme.overlay, 0.65),
                            18.,
                            1.,
                        );
                        let compact = group.rect.w < 320. || group.rect.h < 180.;
                        let title = Rect::new(
                            group.rect.x + 8.,
                            group.rect.y + 4.,
                            group.rect.w - 16.,
                            if compact { 28. } else { 52. },
                        );
                        let badge = Rect::new(
                            title.x + 2.,
                            title.y + 3.,
                            if compact { 24. } else { 36. },
                            if compact { 24. } else { 36. },
                        );
                        canvas.rounded(
                            badge,
                            mix(
                                theme.surface,
                                theme.accent,
                                if current { 0.25 } else { 0.10 },
                            ),
                            8.,
                        );
                        canvas.centered(
                            badge,
                            &group.name,
                            if compact { 13. } else { 17. },
                            theme.accent,
                        );
                        let set = group
                            .set
                            .as_deref()
                            .map(|id| snapshot.set_name(id))
                            .unwrap_or("Shared");
                        let visible = if group.set.as_deref() == Some(snapshot.current_set.as_str())
                            || group.set.is_none()
                        {
                            snapshot
                                .monitors
                                .iter()
                                .find(|m| m.active_workspace.id == group.id)
                                .map(|m| m.name.as_str())
                        } else {
                            group
                                .set
                                .as_deref()
                                .and_then(|id| snapshot.sets.iter().find(|s| s.id == id))
                                .and_then(|s| {
                                    s.monitors.iter().find(|(_, slot)| **slot == group.name)
                                })
                                .map(|(monitor, _)| monitor.as_str())
                        };
                        let placement = visible
                            .map(|m| {
                                format!(
                                    "{}: {m}",
                                    if group.set.as_deref() == Some(snapshot.current_set.as_str()) {
                                        "On"
                                    } else {
                                        "Saved"
                                    }
                                )
                            })
                            .unwrap_or_else(|| group.monitor.clone());
                        if compact {
                            canvas.text(
                                title.x + 34.,
                                title.y + 5.,
                                &format!("{} win · {}", group.cards.len(), placement),
                                11.,
                                theme.muted,
                                title.w - 36.,
                            );
                        } else {
                            canvas.text(
                                title.x + 50.,
                                title.y + 1.,
                                &if ui.set_panels.is_empty() {
                                    format!("{} · Workspace {}", set, group.name)
                                } else {
                                    format!("Workspace {}", group.name)
                                },
                                16.,
                                theme.text,
                                title.w - 52.,
                            );
                            canvas.text(
                                title.x + 50.,
                                title.y + 27.,
                                &format!(
                                    "{} windows  ·  {}{}",
                                    group.cards.len(),
                                    placement,
                                    if current { "  ·  Current" } else { "" }
                                ),
                                12.,
                                theme.muted,
                                title.w - 52.,
                            );
                        }
                        ui.hits.push((title, Action::Workspace(group.id)));
                        canvas.rounded(group.canvas, mix(theme.base, theme.surface, 0.12), 12.);
                    }
                    for card in &group.cards {
                        paint_card(
                            &mut canvas,
                            &mut self.resizer,
                            &mut self.resized,
                            snapshot,
                            captures,
                            card,
                            ui.selected,
                            ui.mode == ViewMode::Windows,
                        );
                        ui.hits.push((card.rect, Action::Select(card.index)));
                        if card.rect.w > 170. && card.rect.h >= 120. {
                            let inspect = Rect::new(
                                card.rect.x + card.rect.w - 36.,
                                card.rect.y + card.rect.h - 30.,
                                28.,
                                23.,
                            );
                            canvas.expand_button(inspect);
                            ui.hits.push((inspect, Action::Inspect(card.index)));
                        }
                    }
                }
                if ui.groups.is_empty() {
                    let empty = Rect::new(w / 2. - 200., h / 2. - 40., 400., 80.);
                    canvas.centered(empty, "No matching windows", 23., theme.text);
                }
                canvas.fill(
                    Rect::new(32., h - 64., w - 64., 1.),
                    mix(theme.base, theme.overlay, 0.55),
                );
                let mut x = 32.;
                for (key, hint, step) in [
                    ("1–9", "Focus window", 182.),
                    ("Space", "Expand", 150.),
                    ("Tab/Shift+Tab", "View", 205.),
                    ("PgUp/PgDn", "Browse", 210.),
                    ("Ctrl+A", "All sets", 160.),
                    ("Esc", "Back", 110.),
                ] {
                    let key_width = match key {
                        "Tab/Shift+Tab" => 110.,
                        "PgUp/PgDn" => 90.,
                        "Space" | "Ctrl+A" => 56.,
                        _ => 42.,
                    };
                    let key_rect = Rect::new(x, h - 46., key_width, 26.);
                    canvas.rounded(key_rect, mix(theme.base, theme.surface, 0.75), 7.);
                    canvas.centered(key_rect, key, 12., theme.text);
                    canvas.text(
                        x + key_width + 9.,
                        h - 42.,
                        hint,
                        13.,
                        mix(theme.base, theme.muted, 0.76),
                        step - key_width - 12.,
                    );
                    x += step;
                }
                if ui.workspace.is_some() {
                    let rect = Rect::new(w - 190., h - 51., 164., 34.);
                    canvas.button(rect, "All workspaces", true);
                    ui.hits.push((rect, Action::All));
                }
            }
            if !ui.error.is_empty() {
                canvas.text(32., h - 89., &ui.error, 17., theme.red, w - 52.);
            }
        }
        self.last_render_ms = start.elapsed().as_secs_f64() * 1000.;
        // A capture generation invalidates the previous scaled copy. Do not keep
        // a new full-size allocation for every second the overview stays open.
        self.resized.retain(|(address, _, _, generation), _| {
            captures
                .get(address)
                .is_some_and(|c| c.generation == *generation)
        });
        canvas.image
    }
}

struct Canvas<'a> {
    theme: desktop_theme::Palette,
    image: RgbaImage,
    scale: f32,
    font: &'a Font,
    glyphs: &'a mut GlyphCache,
}
impl Canvas<'_> {
    fn fill(&mut self, r: Rect, color: [u8; 3]) {
        let (x, y, w, h) = self.pixels(r);
        for yy in y..(y + h).min(self.image.height()) {
            for xx in x..(x + w).min(self.image.width()) {
                self.image
                    .put_pixel(xx, yy, Rgba([color[0], color[1], color[2], 255]));
            }
        }
    }
    fn pixels(&self, r: Rect) -> (u32, u32, u32, u32) {
        (
            (r.x * self.scale).round().max(0.) as u32,
            (r.y * self.scale).round().max(0.) as u32,
            (r.w * self.scale).round().max(1.) as u32,
            (r.h * self.scale).round().max(1.) as u32,
        )
    }
    fn rounded(&mut self, r: Rect, color: [u8; 3], radius: f32) {
        self.shape(r, color, radius, None, 1.);
    }
    fn outline(&mut self, r: Rect, color: [u8; 3], radius: f32, thickness: f32) {
        self.shape(r, color, radius, Some(thickness), 1.);
    }
    fn shadow(&mut self, r: Rect, radius: f32, opacity: f32) {
        for spread in [6., 3., 1.] {
            self.shape(
                Rect::new(
                    r.x - spread,
                    r.y + 3. - spread,
                    r.w + 2. * spread,
                    r.h + 2. * spread,
                ),
                [0, 0, 0],
                radius + spread,
                Some(spread + 4.),
                opacity / 3.,
            );
        }
    }
    fn shape(&mut self, r: Rect, color: [u8; 3], radius: f32, stroke: Option<f32>, opacity: f32) {
        let bounds = Rect::new(
            r.x * self.scale,
            r.y * self.scale,
            r.w * self.scale,
            r.h * self.scale,
        );
        let radius = (radius * self.scale).min(bounds.w / 2.).min(bounds.h / 2.);
        let stroke = stroke.map(|n| n * self.scale);
        let inner = stroke.map(|n| bounds.inset(n));
        let inner_radius = stroke.map(|n| (radius - n).max(0.)).unwrap_or(0.);
        for y in (bounds.y.floor().max(0.) as u32)
            ..((bounds.y + bounds.h).ceil() as u32).min(self.image.height())
        {
            let inset = rounded_inset(y as f32 + 0.5, bounds, radius);
            let left = (bounds.x + inset - 1.).floor().max(0.) as u32;
            let right =
                ((bounds.x + bounds.w - inset + 1.).ceil().max(0.) as u32).min(self.image.width());
            let gap = inner
                .filter(|r| y as f32 + 0.5 >= r.y + 1. && (y as f32 + 0.5) <= r.y + r.h - 1.)
                .map(|r| {
                    let inset = rounded_inset(y as f32 + 0.5, r, inner_radius);
                    (
                        (r.x + inset + 1.).ceil().max(0.) as u32,
                        (r.x + r.w - inset - 1.).floor().max(0.) as u32,
                    )
                });
            let spans = if let Some((a, b)) = gap.filter(|(a, b)| a < b) {
                [(left, right.min(a)), (left.max(b), right)]
            } else {
                [(left, right), (0, 0)]
            };
            for (start, end) in spans {
                for x in start..end {
                    let outer = if x as f32 > bounds.x + radius + 1.
                        && (x as f32) < bounds.x + bounds.w - radius - 1.
                        && y as f32 > bounds.y + 1.
                        && (y as f32) < bounds.y + bounds.h - 1.
                    {
                        1.
                    } else {
                        rounded_coverage(x as f32 + 0.5, y as f32 + 0.5, bounds, radius)
                    };
                    let alpha = (outer
                        - inner
                            .map(|r| {
                                rounded_coverage(x as f32 + 0.5, y as f32 + 0.5, r, inner_radius)
                            })
                            .unwrap_or(0.))
                    .max(0.)
                        * opacity;
                    if alpha >= 1. {
                        self.image
                            .put_pixel(x, y, Rgba([color[0], color[1], color[2], 255]));
                    } else if alpha > 0. {
                        let dst = self.image.get_pixel_mut(x, y);
                        for c in 0..3 {
                            dst[c] = (dst[c] as f32 * (1. - alpha) + color[c] as f32 * alpha)
                                .round() as u8;
                        }
                    }
                }
            }
        }
    }
    fn centered(&mut self, r: Rect, label: &str, size: f32, color: [u8; 3]) {
        let width: f32 = label
            .chars()
            .map(|c| {
                self.font
                    .metrics(c, size * self.scale)
                    .advance_width
                    .round()
                    / self.scale
            })
            .sum();
        self.text(
            r.x + ((r.w - width) / 2.).max(0.),
            r.y + (r.h - size) / 2. - 2.,
            label,
            size,
            color,
            r.w,
        );
    }
    fn text(&mut self, x: f32, y: f32, text: &str, size: f32, color: [u8; 3], max_width: f32) {
        let px = (size * self.scale).round() as u32;
        let mut cursor = (x * self.scale).round() as i32;
        let baseline = ((y + size) * self.scale).round() as i32;
        let right = ((x + max_width) * self.scale) as i32;
        for ch in text.chars().filter(|c| !c.is_control()) {
            let (metrics, bitmap) = self
                .glyphs
                .entry((ch, px))
                .or_insert_with(|| self.font.rasterize(ch, px as f32));
            if cursor + metrics.advance_width as i32 > right {
                break;
            }
            for yy in 0..metrics.height {
                for xx in 0..metrics.width {
                    let dx = cursor + metrics.xmin + xx as i32;
                    let dy = baseline - metrics.height as i32 - metrics.ymin + yy as i32;
                    if dx < 0
                        || dy < 0
                        || dx >= self.image.width() as i32
                        || dy >= self.image.height() as i32
                    {
                        continue;
                    }
                    let alpha = bitmap[yy * metrics.width + xx] as u32;
                    let dst = self.image.get_pixel_mut(dx as u32, dy as u32);
                    for c in 0..3 {
                        dst[c] = ((color[c] as u32 * alpha + dst[c] as u32 * (255 - alpha) + 127)
                            / 255) as u8;
                    }
                }
            }
            cursor += metrics.advance_width.round() as i32;
        }
    }
    fn expand_button(&mut self, r: Rect) {
        self.rounded(r, mix(self.theme.surface, self.theme.accent, 0.08), 7.);
        let color = self.theme.text;
        for (x, y, right, bottom) in [
            (r.x + 7., r.y + 6., false, false),
            (r.x + r.w - 7., r.y + 6., true, false),
            (r.x + 7., r.y + r.h - 6., false, true),
            (r.x + r.w - 7., r.y + r.h - 6., true, true),
        ] {
            self.rounded(
                Rect::new(
                    x - if right { 5. } else { 0. },
                    y - if bottom { 1.5 } else { 0. },
                    5.,
                    1.5,
                ),
                color,
                0.75,
            );
            self.rounded(
                Rect::new(
                    x - if right { 1.5 } else { 0. },
                    y - if bottom { 5. } else { 0. },
                    1.5,
                    5.,
                ),
                color,
                0.75,
            );
        }
    }
    fn button(&mut self, r: Rect, label: &str, active: bool) {
        self.rounded(
            r,
            if active {
                self.theme.accent
            } else {
                mix(self.theme.surface, self.theme.accent, 0.08)
            },
            8.,
        );
        self.centered(
            r,
            label,
            13.,
            if active {
                self.theme.base
            } else {
                self.theme.text
            },
        );
    }
}

fn mix(a: [u8; 3], b: [u8; 3], t: f32) -> [u8; 3] {
    std::array::from_fn(|i| (a[i] as f32 * (1. - t) + b[i] as f32 * t).round() as u8)
}

fn rounded_inset(y: f32, r: Rect, radius: f32) -> f32 {
    let edge = (y - r.y - r.h / 2.).abs() - r.h / 2. + radius;
    if edge > 0. {
        radius - (radius * radius - edge * edge).max(0.).sqrt()
    } else {
        0.
    }
}

fn rounded_coverage(x: f32, y: f32, r: Rect, radius: f32) -> f32 {
    let radius = radius.min(r.w / 2.).min(r.h / 2.);
    let dx = (x - r.x - r.w / 2.).abs() - r.w / 2. + radius;
    let dy = (y - r.y - r.h / 2.).abs() - r.h / 2. + radius;
    let distance = if dx > 0. && dy > 0. {
        dx.hypot(dy) - radius
    } else {
        dx.max(dy) - radius
    };
    (0.5 - distance).clamp(0., 1.)
}

fn paint_card(
    canvas: &mut Canvas,
    resizer: &mut fir::Resizer,
    cache: &mut ImageCache,
    snapshot: &Snapshot,
    captures: &HashMap<String, Capture>,
    card: &Card,
    selected: usize,
    flat: bool,
) {
    let client = &snapshot.clients[card.index];
    let r = card.rect;
    let selected = selected == card.index;
    let theme = canvas.theme.clone();
    // Match the desktop's 10px window rounding; nested images keep an 8px inset.
    let radius = 10.;
    canvas.shadow(r, radius, if selected { 0.22 } else { 0.12 });
    canvas.rounded(
        r,
        if selected {
            mix(theme.surface, theme.accent, 0.12)
        } else {
            theme.surface
        },
        radius,
    );
    if r.h < 32. || r.w < 60. {
        canvas.centered(
            r,
            &card.number.to_string(),
            (r.h - 2.).clamp(6., 12.),
            if selected { theme.accent } else { theme.text },
        );
        canvas.outline(
            r,
            if selected {
                theme.accent
            } else {
                theme.overlay
            },
            radius.min(r.h / 2.),
            1.,
        );
        return;
    }
    let compact = r.h < 120. || r.w < 150.;
    let header = if compact { 26. } else { 38. };
    let footer = if compact { 0. } else { 34. };
    let content = Rect::new(
        r.x + 4.,
        r.y + header,
        r.w - 8.,
        (r.h - header - footer).max(1.),
    );
    canvas.rounded(content, theme.base, 8.);
    if r.h > header + footer + 2. {
        if let Some(capture) = captures.get(&client.address) {
            let image = content.fit(capture.width as f32, capture.height as f32);
            paint_capture(
                canvas,
                resizer,
                cache,
                &client.address,
                capture,
                image,
                content,
                false,
                8.,
            );
        } else if r.w > 100. {
            canvas.centered(content, "Capturing…", 14., theme.muted);
        }
    }
    let number = Rect::new(
        r.x + 8.,
        r.y + 6.,
        if compact { 24. } else { 30. },
        if compact { 18. } else { 25. },
    );
    canvas.rounded(
        number,
        if selected {
            theme.accent
        } else {
            mix(theme.surface, theme.overlay, 0.8)
        },
        7.,
    );
    canvas.centered(
        number,
        &card.number.to_string(),
        if compact { 12. } else { 14. },
        if selected { theme.base } else { theme.text },
    );
    canvas.text(
        number.x + number.w + 9.,
        r.y + if compact { 5. } else { 8. },
        client.app(),
        if compact { 12. } else { 15. },
        theme.text,
        r.w - number.w - 30.,
    );
    if !compact {
        let states = client.states();
        let context = if flat {
            format!("{} · {}", snapshot.context(&client.workspace), client.title)
        } else if states.is_empty() {
            format!("{} · {}", card.slot, client.title)
        } else {
            format!("{} · {} · {}", card.slot, states, client.title)
        };
        canvas.text(
            r.x + 10.,
            r.y + r.h - 26.,
            &context,
            12.,
            mix(theme.surface, theme.muted, 0.85),
            r.w - if r.w > 170. { 50. } else { 20. },
        );
    }
    if card.overlap && r.w > 230. && !compact {
        let tag = Rect::new(content.x + 8., content.y + 8., 152., 22.);
        canvas.rounded(tag, theme.base, 6.);
        canvas.centered(tag, "Overlapping / grouped", 11., theme.yellow);
    }
    canvas.outline(
        r,
        if selected {
            theme.accent
        } else {
            mix(theme.overlay, theme.muted, 0.14)
        },
        radius,
        if selected { 2. } else { 1. },
    );
}

fn paint_capture(
    canvas: &mut Canvas,
    resizer: &mut fir::Resizer,
    cache: &mut ImageCache,
    address: &str,
    capture: &Capture,
    r: Rect,
    clip: Rect,
    native: bool,
    radius: f32,
) {
    let scale = canvas.scale;
    let w = (r.w * scale).round().max(1.) as u32;
    let h = (r.h * scale).round().max(1.) as u32;
    let source = if native || (w == capture.width && h == capture.height) {
        &capture.pixels
    } else {
        cache
            .entry((address.to_owned(), w, h, capture.generation))
            .or_insert_with(|| {
                let src = fir::images::ImageRef::new(
                    capture.width,
                    capture.height,
                    &capture.pixels,
                    fir::PixelType::U8x4,
                )
                .unwrap();
                let mut dst = fir::images::Image::new(w, h, fir::PixelType::U8x4);
                let options = fir::ResizeOptions::new()
                    .resize_alg(fir::ResizeAlg::Convolution(fir::FilterType::Lanczos3))
                    .use_alpha(false);
                resizer.resize(&src, &mut dst, &options).unwrap();
                dst.into_vec()
            })
    };
    let clip = Rect::new(
        clip.x * scale,
        clip.y * scale,
        clip.w * scale,
        clip.h * scale,
    );
    let x = (r.x * scale).round() as i32;
    let y = (r.y * scale).round() as i32;
    if radius == 0. {
        blit(&mut canvas.image, source, w, h, x, y, clip);
    } else {
        blit_rounded(&mut canvas.image, source, w, h, x, y, clip, radius * scale);
    }
}

fn blit(dst: &mut RgbaImage, source: &[u8], sw: u32, sh: u32, x: i32, y: i32, clip: Rect) {
    let left = x.max(clip.x.ceil() as i32).max(0);
    let top = y.max(clip.y.ceil() as i32).max(0);
    let right = (x + sw as i32)
        .min((clip.x + clip.w).floor() as i32)
        .min(dst.width() as i32);
    let bottom = (y + sh as i32)
        .min((clip.y + clip.h).floor() as i32)
        .min(dst.height() as i32);
    if left >= right || top >= bottom {
        return;
    }
    let dw = dst.width() as usize;
    for dy in top..bottom {
        let a = ((dy - y) as usize * sw as usize + (left - x) as usize) * 4;
        let b = (dy as usize * dw + left as usize) * 4;
        let len = (right - left) as usize * 4;
        dst.as_mut()[b..b + len].copy_from_slice(&source[a..a + len]);
    }
}

// Copy each scanline directly, blending only the antialiased corner pixels.
fn blit_rounded(
    dst: &mut RgbaImage,
    source: &[u8],
    sw: u32,
    sh: u32,
    x: i32,
    y: i32,
    clip: Rect,
    radius: f32,
) {
    let bounds = Rect::new(x as f32, y as f32, sw as f32, sh as f32);
    let radius = radius.min(bounds.w / 2.).min(bounds.h / 2.);
    for row in y.max(clip.y.ceil() as i32).max(0)
        ..(y + sh as i32)
            .min((clip.y + clip.h).floor() as i32)
            .min(dst.height() as i32)
    {
        let edge = (row as f32 + 0.5 - bounds.y - bounds.h / 2.).abs() - bounds.h / 2. + radius;
        let inset = if edge > 0. {
            radius - (radius * radius - edge * edge).max(0.).sqrt()
        } else {
            0.
        };
        let left = (x + inset.floor() as i32).max(clip.x.ceil() as i32).max(0);
        let right = (x + sw as i32 - inset.floor() as i32)
            .min((clip.x + clip.w).floor() as i32)
            .min(dst.width() as i32);
        if right <= left {
            continue;
        }
        let a = ((row - y) as usize * sw as usize + (left - x) as usize) * 4;
        let b = (row as usize * dst.width() as usize + left as usize) * 4;
        let len = (right - left) as usize * 4;
        // Preserve the background under the two boundary pixels for edge blending.
        let first = *dst.get_pixel(left as u32, row as u32);
        let last = *dst.get_pixel((right - 1) as u32, row as u32);
        dst.as_mut()[b..b + len].copy_from_slice(&source[a..a + len]);
        for (column, background) in [(left, first), (right - 1, last)] {
            let alpha = rounded_coverage(column as f32 + 0.5, row as f32 + 0.5, bounds, radius);
            let pixel = dst.get_pixel_mut(column as u32, row as u32);
            for c in 0..3 {
                pixel[c] =
                    (pixel[c] as f32 * alpha + background[c] as f32 * (1. - alpha)).round() as u8;
            }
        }
    }
}

#[derive(Serialize)]
pub struct CaptureInfo<'a> {
    pub address: &'a str,
    pub width: u32,
    pub height: u32,
    pub generation: u64,
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn sequential_navigation_wraps_and_respects_scope_and_search() {
        let mut ui = Ui {
            snapshot: Some(crate::layout::tests::sets_fixture()),
            selected: 1,
            ..Ui::default()
        };
        ui.browse(Browse::Next);
        assert_eq!(ui.selected, 0);
        ui.browse(Browse::Previous);
        assert_eq!(ui.selected, 1);
        ui.all_sets = true;
        ui.browse(Browse::Last);
        assert_eq!(ui.selected, 2);
        ui.browse(Browse::First);
        assert_eq!(ui.selected, 0);
        ui.query = "School".into();
        ui.pan = [100., 50.];
        ui.browse(Browse::Next);
        assert_eq!(ui.selected, 2);
        assert_eq!(ui.pan, [0., 0.]);
        ui.browse(Browse::Previous);
        assert_eq!(ui.selected, 2);
        ui.query = "No matching window".into();
        ui.browse(Browse::Last); // Empty results must not index or wrap an empty list.
        assert_eq!(ui.selected, 2);
    }
    #[test]
    fn rounded_previews_preserve_background_corners_and_source_interior() {
        for scale in [1, 2] {
            let size = 20 * scale;
            let background = Rgba([30, 40, 50, 255]);
            let foreground = Rgba([200, 210, 220, 255]);
            let mut dst = RgbaImage::from_pixel(size, size, background);
            let source = RgbaImage::from_pixel(size, size, foreground);
            blit_rounded(
                &mut dst,
                source.as_raw(),
                size,
                size,
                0,
                0,
                Rect::new(0., 0., size as f32, size as f32),
                8. * scale as f32,
            );
            assert_eq!(*dst.get_pixel(0, 0), background);
            assert_eq!(*dst.get_pixel(size - 1, size - 1), background);
            assert_eq!(*dst.get_pixel(size / 2, size / 2), foreground);
            assert_eq!(*dst.get_pixel(size / 2, 0), foreground);
            assert!(dst
                .pixels()
                .any(|p| p[0] > background[0] && p[0] < foreground[0]));
        }
    }

    #[test]
    fn native_view_copies_exact_pixels_without_filtering() {
        let source: Vec<u8> = (0..64).collect();
        let mut dst = RgbaImage::new(2, 2);
        blit(&mut dst, &source, 4, 4, -1, -1, Rect::new(0., 0., 2., 2.));
        assert_eq!(&dst.as_raw()[0..8], &source[20..28]);
        assert_eq!(&dst.as_raw()[8..16], &source[36..44]);
    }
}
