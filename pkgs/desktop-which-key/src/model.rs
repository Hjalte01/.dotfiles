use anyhow::{bail, Result};
use serde::Serialize;
use std::{
    collections::HashMap,
    path::PathBuf,
    time::{Duration, Instant},
};

#[derive(Clone, Debug, Serialize)]
pub struct Binding {
    pub combo: String,
    pub description: String,
    pub group: String,
    pub submap: String,
    pub mods: String,
    pub key: String,
    pub dispatcher: String,
    pub arg: String,
    pub flags: String,
    pub line: usize,
}
impl Binding {
    pub fn executable(&self) -> bool {
        !self.flags.contains('m') && !self.flags.contains('r') && self.dispatcher != "global"
    }
    pub fn matches(&self, query: &str) -> bool {
        let haystack = format!(
            "{} {} {} {} {}",
            self.combo, self.description, self.group, self.dispatcher, self.arg
        )
        .to_lowercase();
        query
            .to_lowercase()
            .split_whitespace()
            .all(|word| haystack.contains(word))
    }
}
pub fn config_path() -> PathBuf {
    std::env::var_os("HYPRLAND_CONFIG")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            PathBuf::from(std::env::var_os("HOME").unwrap_or_default())
                .join(".config/hypr/hyprland.conf")
        })
}
pub fn load() -> Result<Vec<Binding>> {
    parse(&std::fs::read_to_string(config_path())?)
}
fn mods(value: &str) -> String {
    let words = value.to_uppercase();
    [
        ("SUPER", "Super"),
        ("CTRL", "Ctrl"),
        ("ALT", "Alt"),
        ("SHIFT", "Shift"),
    ]
    .into_iter()
    .filter(|(raw, _)| words.split_whitespace().any(|s| s == *raw))
    .map(|(_, label)| label)
    .collect::<Vec<_>>()
    .join("+")
}
fn key(value: &str) -> String {
    match value.to_lowercase().as_str() {
        "return" => "Enter".into(),
        "space" => "Space".into(),
        "escape" => "Esc".into(),
        "comma" => ",".into(),
        "period" => ".".into(),
        _ if value.len() == 1 => value.to_uppercase(),
        _ => value.into(),
    }
}
fn category(description: &str, submap: &str) -> String {
    if !submap.is_empty() {
        return format!("Sequences · {submap}");
    }
    let d = description.to_lowercase();
    if [
        "go to website",
        "audio hierarchy",
        "pointer automation",
        "desktop controls",
        "codex tools",
        "system power menu",
    ]
    .contains(&d.as_str())
    {
        return "Groups".into();
    }
    if d.contains("key map") || d.contains("keybind") {
        return "Groups & desktop".into();
    }
    for (group, words) in [
        ("Workspaces", "workspace"),
        ("Windows", "focus |swap window|resize|fullscreen|close window|split|move window|window width|window height"),
        ("Clipboard & Codex", "clipboard|codex|paste latest"),
        ("Notifications & capture", "notification|screenshot|math ocr"),
        ("Daily apps", "terminal|downloads|editor|activity|docker|zathura|pdf|files|dictation|website|app launcher"),
        ("Groups & desktop", "display|desktop|bluetooth|night|touchscreen|waybar|pointer|automation|keybind|system power|audio|microphone|mute"),
    ] { if words.split('|').any(|w| d.contains(w)) { return group.into(); } }
    "Hardware & other".into()
}
pub fn parse(text: &str) -> Result<Vec<Binding>> {
    let mut bindings = Vec::new();
    let mut submap = String::new();
    let mut prefix = String::new();
    let mut variables: HashMap<String, String> = HashMap::new();
    for (index, raw) in text.lines().enumerate() {
        let raw = raw.trim();
        if raw.starts_with('#') || raw.is_empty() {
            continue;
        }
        if let Some((left, right)) = raw.split_once('=') {
            if left.trim().starts_with('$') {
                variables.insert(left.trim().into(), right.trim().into());
                continue;
            }
            if left.trim() == "submap" {
                let name = right.split('#').next().unwrap().trim();
                submap = if name == "reset" {
                    String::new()
                } else {
                    name.into()
                };
                prefix = raw
                    .split_once("# keybind-prefix:")
                    .map(|(_, s)| s.trim().to_owned())
                    .unwrap_or_default();
                continue;
            }
            let Some(flags) = left.trim().strip_prefix("bind") else {
                continue;
            };
            // Non-consuming controller hooks are implementation details, not actions.
            if flags.contains('n') || flags.contains('t') {
                continue;
            }
            let (body, annotation) = right.split_once(" # keybind:").unwrap_or((right, ""));
            let mut fields = body
                .splitn(if flags.contains('d') { 5 } else { 4 }, ',')
                .map(str::trim);
            let Some(modifiers) = fields.next() else {
                continue;
            };
            let Some(raw_key) = fields.next() else {
                continue;
            };
            if raw_key == "catchall" || raw_key.starts_with("switch:") {
                continue;
            }
            let description = if flags.contains('d') {
                fields.next().unwrap_or("")
            } else {
                annotation.trim()
            };
            let dispatcher = fields.next().unwrap_or("");
            let arg = fields.next().unwrap_or("").trim();
            if dispatcher == "exec" && arg == "true" {
                continue;
            }
            if description.is_empty() {
                bail!("Binding on line {} needs a description", index + 1);
            }
            let modifiers = mods(modifiers);
            let key = key(raw_key);
            let chord = if modifiers.is_empty() {
                key.clone()
            } else {
                format!("{modifiers}+{key}")
            };
            let combo = if submap.is_empty() {
                chord
            } else {
                format!("{prefix} → {chord}")
            };
            bindings.push(Binding {
                combo,
                description: description.into(),
                group: category(description, &submap),
                submap: submap.clone(),
                mods: modifiers,
                key,
                dispatcher: dispatcher.into(),
                arg: expand(arg, &variables),
                flags: flags.into(),
                line: index + 1,
            });
        }
    }
    Ok(bindings)
}
fn expand(value: &str, variables: &HashMap<String, String>) -> String {
    let mut out = String::new();
    let mut chars = value.chars().peekable();
    while let Some(ch) = chars.next() {
        if ch != '$' {
            out.push(ch);
            continue;
        }
        let mut name = String::from("$");
        while chars
            .peek()
            .is_some_and(|c| c.is_alphanumeric() || *c == '_')
        {
            name.push(chars.next().unwrap());
        }
        out.push_str(variables.get(&name).map(String::as_str).unwrap_or(&name));
    }
    out
}
pub fn validate(bindings: &[Binding]) -> Result<()> {
    let mut seen = HashMap::new();
    for b in bindings {
        let identity = (
            b.submap.to_lowercase(),
            b.mods.clone(),
            b.key.to_lowercase(),
            b.flags.contains('r'),
        );
        if let Some(previous) = seen.insert(identity, b.line) {
            bail!("Duplicate {} on lines {} and {}", b.combo, previous, b.line);
        }
        if b.mods.split('+').count() > 2 {
            bail!("Too many modifiers: {}", b.combo);
        }
        if !b.submap.is_empty() && !b.combo.starts_with("Super+") {
            bail!("Missing prefix: {}", b.combo);
        }
    }
    // Universal aliases can also collide with ignore-modifier continuation keys.
    for global in bindings
        .iter()
        .filter(|b| b.submap.is_empty() && b.flags.contains('u'))
    {
        for local in bindings.iter().filter(|b| !b.submap.is_empty()) {
            if global.key.eq_ignore_ascii_case(&local.key)
                && (local.flags.contains('i') || global.mods == local.mods)
                && !(local.key == "Esc" && local.description.starts_with("Cancel"))
            {
                bail!(
                    "Universal {} overlaps {} on lines {} and {}",
                    global.combo,
                    local.combo,
                    global.line,
                    local.line
                );
            }
        }
    }
    for name in bindings
        .iter()
        .filter(|b| !b.submap.is_empty())
        .map(|b| &b.submap)
    {
        if !bindings.iter().any(|b| &b.submap == name && b.key == "Esc") {
            bail!("Submap {name} has no Escape cancellation");
        }
    }
    Ok(())
}
#[derive(Default, Debug, PartialEq, Eq, Clone, Serialize)]
pub enum Mode {
    #[default]
    Hidden,
    Peek,
    Pinned,
    Context(String),
}
#[derive(Default)]
pub struct Ui {
    pub mode: Mode,
    pub query: String,
    pub search: bool,
    pub help: bool,
    pub selected: usize,
    pub page_size: usize,
    pub deadline: Option<Instant>,
    pub error: String,
}
impl Ui {
    pub fn hold_start(&mut self) {
        if self.mode == Mode::Hidden {
            self.deadline = Some(Instant::now() + Duration::from_millis(250));
        }
    }
    pub fn hold_end(&mut self) {
        self.deadline = None;
        if self.mode == Mode::Peek {
            self.mode = Mode::Hidden;
        }
    }
    pub fn open(&mut self, mode: Mode) {
        self.mode = mode;
        self.deadline = None;
        self.query.clear();
        self.search = false;
        self.help = false;
        self.selected = 0;
        self.error.clear();
    }
    pub fn filtered<'a>(&self, bindings: &'a [Binding]) -> Vec<&'a Binding> {
        let mut rows: Vec<_> = bindings
            .iter()
            // Sequence cancellation is already explained in the footer.
            .filter(|b| !(b.key == "Esc" && !b.submap.is_empty()))
            .filter(|b| match &self.mode {
                Mode::Peek => b.submap.is_empty() && b.mods == "Super",
                Mode::Context(name) => &b.submap == name,
                _ => true,
            })
            .filter(|b| b.matches(&self.query))
            .collect();
        rows.sort_by(|a, b| (&a.group, &a.combo).cmp(&(&b.group, &b.combo)));
        rows
    }
    pub fn move_by(&mut self, delta: isize, len: usize) {
        self.selected =
            (self.selected as isize + delta).clamp(0, len.saturating_sub(1) as isize) as usize;
    }
    pub fn escape(&mut self) {
        if self.help {
            self.help = false;
        } else if self.search || !self.query.is_empty() {
            self.query.clear();
            self.search = false;
            self.selected = 0;
        } else {
            self.open(Mode::Hidden);
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn collision_is_case_and_modifier_order_insensitive() {
        let b = parse("bindd = CTRL SUPER, Z, PDFs, exec, pdfpick\nbind = SUPER CTRL, z, exec, circle # keybind: Circle").unwrap();
        assert!(validate(&b).unwrap_err().to_string().contains("Duplicate"));
    }
    #[test]
    fn sequences_preserve_modifiers_and_commas() {
        let b = parse("submap = tools # keybind-prefix: Super+X\nbindd = SHIFT, c, Circle, exec, hyprctl keyword foo 1,2\nbindd = , Escape, Cancel, submap, reset\nsubmap = reset\nbind = SUPER, f, fullscreen # keybind: Fullscreen").unwrap();
        assert_eq!(b[0].combo, "Super+X → Shift+C");
        assert_eq!(b[0].arg, "hyprctl keyword foo 1,2");
        assert!(validate(&b).is_ok());
        assert_eq!(b[2].dispatcher, "fullscreen");
    }
    #[test]
    fn search_finds_keys_values_and_sequences() {
        let b = parse(
            "submap = tools # keybind-prefix: Super+X\nbindd = , c, Cursor circle, exec, circle",
        )
        .unwrap();
        assert!(b[0].matches("super+x circle"));
        assert!(b[0].matches("CURSOR"));
        assert!(!b[0].matches("pdf"));
    }
    #[test]
    fn universal_alias_cannot_shadow_an_ignore_modifier_sequence() {
        let text = "submap = audio # keybind-prefix: Super+A\nbinddi = , m, Microphone, exec, microphone\nbinddi = , Escape, Cancel audio shortcut, submap, reset\nsubmap = reset\nbinddu = SUPER, M, Pin map, exec, map";
        assert!(validate(&parse(text).unwrap())
            .unwrap_err()
            .to_string()
            .contains("overlaps"));
        assert!(validate(&parse(&text.replace("binddu", "bindd")).unwrap()).is_ok());
    }
    #[test]
    fn variable_expansion_keeps_shell_variables_and_searches_commands() {
        let b = parse(
            "$terminal = ghostty\nbindd = SUPER, Return, Terminal, exec, $terminal -e btop $HOME",
        )
        .unwrap();
        assert_eq!(b[0].arg, "ghostty -e btop $HOME");
        assert!(b[0].matches("btop"));
    }
    #[test]
    fn pin_and_context_survive_super_release_and_late_timer() {
        let mut ui = Ui::default();
        ui.hold_start();
        assert!(ui.deadline.is_some());
        ui.open(Mode::Pinned);
        ui.hold_end();
        assert_eq!(ui.mode, Mode::Pinned);
        assert!(ui.deadline.is_none());
        ui.open(Mode::Context("web".into()));
        ui.hold_end();
        assert_eq!(ui.mode, Mode::Context("web".into()));
        ui.open(Mode::Peek);
        ui.hold_end();
        assert_eq!(ui.mode, Mode::Hidden);
    }
    #[test]
    fn escape_unwinds_help_search_then_closes() {
        let mut ui = Ui::default();
        ui.open(Mode::Pinned);
        ui.help = true;
        ui.search = true;
        ui.query = "pdf".into();
        ui.escape();
        assert!(!ui.help);
        assert_eq!(ui.query, "pdf");
        ui.escape();
        assert!(ui.query.is_empty());
        assert_eq!(ui.mode, Mode::Pinned);
        ui.escape();
        assert_eq!(ui.mode, Mode::Hidden);
    }
}
