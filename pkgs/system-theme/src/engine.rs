use anyhow::{bail, Context, Result};
use serde_json::{json, Value};
use std::{
    collections::hash_map::DefaultHasher,
    fs::{self, File, OpenOptions},
    hash::{Hash, Hasher},
    io::{Read, Write},
    os::{
        fd::AsRawFd,
        unix::{
            fs::{symlink, FileTypeExt, MetadataExt},
            net::UnixStream,
        },
    },
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    thread,
    time::{Duration, Instant},
};

#[derive(Clone)]
pub struct Engine {
    pub home: PathBuf,
    pub config: PathBuf,
    pub state: PathBuf,
    pub catalog: PathBuf,
    pub current: PathBuf,
    pub palettes: Value,
    pub wallpapers: Vec<(String, String)>,
    pub desktop: bool,
}

pub struct Lock(File);
impl Lock {
    pub fn new(path: &Path, nonblocking: bool) -> Result<Self> {
        fs::create_dir_all(path.parent().unwrap())?;
        let file = OpenOptions::new()
            .create(true)
            .truncate(false)
            .write(true)
            .open(path)?;
        let flags = libc::LOCK_EX | if nonblocking { libc::LOCK_NB } else { 0 };
        if unsafe { libc::flock(file.as_raw_fd(), flags) } != 0 {
            bail!("Another appearance picker is already open");
        }
        Ok(Self(file))
    }
}
impl Drop for Lock {
    fn drop(&mut self) {
        unsafe {
            libc::flock(self.0.as_raw_fd(), libc::LOCK_UN);
        }
    }
}

pub fn write(path: &Path, text: &str) -> Result<()> {
    if fs::read_to_string(path).ok().as_deref() == Some(text) {
        return Ok(());
    }
    fs::create_dir_all(path.parent().context("Missing parent")?)?;
    let temporary = path.with_extension("theme-tmp");
    fs::write(&temporary, text)?;
    fs::rename(temporary, path)?;
    Ok(())
}

pub fn link(target: &Path, path: &Path) -> Result<()> {
    if fs::read_link(path).ok().as_deref() == Some(target) {
        return Ok(());
    }
    fs::create_dir_all(path.parent().context("Missing parent")?)?;
    let temporary = path.with_extension("theme-tmp");
    let _ = fs::remove_file(&temporary);
    symlink(target, &temporary)?;
    fs::rename(temporary, path)?;
    Ok(())
}

fn backup(path: &Path) -> Result<()> {
    let saved = path.with_file_name(format!(
        "{}.before-system-theme",
        path.file_name().unwrap().to_string_lossy()
    ));
    if path.exists() && !saved.exists() {
        fs::copy(path, saved)?;
    }
    Ok(())
}

// Change only named INI keys; preserve comments, sections and unrelated settings.
fn ini(path: &Path, section: &str, settings: &[(&str, &str)]) -> Result<()> {
    let original = fs::read_to_string(path).unwrap_or_default();
    let mut lines: Vec<String> = original.lines().map(str::to_owned).collect();
    let heading = format!("[{section}]");
    let mut start = if section.is_empty() {
        0
    } else if let Some(i) = lines.iter().position(|l| l.trim() == heading) {
        i + 1
    } else {
        lines.push(String::new());
        lines.push(heading);
        lines.len()
    };
    for (key, value) in settings {
        let end = (start..lines.len())
            .find(|&i| lines[i].trim().starts_with('['))
            .unwrap_or(lines.len());
        let line = format!("{key} = {value}");
        if let Some(i) = (start..end).find(|&i| {
            lines[i]
                .split_once('=')
                .is_some_and(|(k, _)| k.trim() == *key)
        }) {
            lines[i] = line;
        } else {
            lines.insert(end, line);
        }
        start = start.min(lines.len());
    }
    backup(path)?;
    write(path, &(lines.join("\n") + "\n"))
}

fn command(program: &str, args: &[&str]) -> bool {
    match Command::new(program)
        .args(args)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
    {
        Ok(status) => status.success(),
        Err(_) => false,
    }
}

// Match the real executable, not Linux's truncated comm field or command arguments.
pub fn executable_matches(path: &Path, name: &str) -> bool {
    path.file_name()
        .and_then(|s| s.to_str())
        .is_some_and(|s| s == name || s == format!(".{name}-wrapped"))
}

pub fn signal_app(name: &str, signal: i32) -> usize {
    let mut sent = 0;
    if let Ok(entries) = fs::read_dir("/proc") {
        for entry in entries.flatten() {
            let Ok(pid) = entry.file_name().to_string_lossy().parse::<i32>() else {
                continue;
            };
            if entry
                .metadata()
                .is_ok_and(|m| m.uid() == unsafe { libc::geteuid() })
                && fs::read_link(entry.path().join("exe"))
                    .is_ok_and(|exe| executable_matches(&exe, name))
                && unsafe { libc::kill(pid, signal) } == 0
            {
                sent += 1;
            }
        }
    }
    sent
}

fn notify_editors() {
    let Some(root) = std::env::var_os("XDG_RUNTIME_DIR") else {
        return;
    };
    let Ok(entries) = fs::read_dir(root) else {
        return;
    };
    // MessagePack-RPC notification: [2, "nvim_exec_lua", [code, []]].
    // This also updates editors started before the faster file watcher existed.
    let code = b"local ok,t=pcall(require,'config.system-theme'); if ok then t.apply() end";
    let mut packet = vec![0x93, 2, 0xad];
    packet.extend_from_slice(b"nvim_exec_lua");
    packet.extend_from_slice(&[0x92, 0xd9, code.len() as u8]);
    packet.extend_from_slice(code);
    packet.push(0x90);
    for entry in entries.flatten() {
        if entry.file_name().to_string_lossy().starts_with("nvim.")
            && entry.file_type().is_ok_and(|t| t.is_socket())
            && entry
                .metadata()
                .is_ok_and(|m| m.uid() == unsafe { libc::geteuid() })
        {
            if let Ok(mut socket) = UnixStream::connect(entry.path()) {
                let _ = socket.set_write_timeout(Some(Duration::from_millis(20)));
                let _ = socket.write_all(&packet);
            }
        }
    }
}

pub fn hypr(request: &str) -> Result<String> {
    let root = std::env::var("XDG_RUNTIME_DIR")?;
    let signature = std::env::var("HYPRLAND_INSTANCE_SIGNATURE")?;
    let mut socket = UnixStream::connect(format!("{root}/hypr/{signature}/.socket.sock"))?;
    socket.set_read_timeout(Some(Duration::from_millis(500)))?;
    socket.set_write_timeout(Some(Duration::from_millis(500)))?;
    socket.write_all(request.as_bytes())?;
    let mut response = String::new();
    socket.read_to_string(&mut response)?;
    Ok(response)
}

impl Engine {
    pub fn new() -> Result<Self> {
        let home = PathBuf::from(std::env::var_os("HOME").context("HOME is unset")?);
        let config = std::env::var_os("XDG_CONFIG_HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|| home.join(".config"));
        let state = std::env::var_os("XDG_STATE_HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|| home.join(".local/state"))
            .join("dotfiles-theme");
        let catalog = config.join("dotfiles-theme/catalog");
        let palettes = serde_json::from_str(&fs::read_to_string(catalog.join("palettes.json"))?)?;
        let wallpapers: Vec<(String, String)> =
            serde_json::from_str(&fs::read_to_string(catalog.join("wallpapers.json"))?)?;
        if wallpapers.is_empty() {
            bail!("The wallpaper catalog is empty");
        }
        let current = config.join("dotfiles-theme/current");
        let desktop = std::env::var("DOTFILES_THEME_DESKTOP").as_deref() == Ok("1");
        Ok(Self {
            home,
            config,
            state,
            catalog,
            current,
            palettes,
            wallpapers,
            desktop,
        })
    }
    pub fn keys(&self) -> Vec<String> {
        self.palettes.as_object().unwrap().keys().cloned().collect()
    }
    pub fn saved(&self) -> Result<Value> {
        let path = self.state.join("state.json");
        if !path.exists() {
            return Ok(json!({"theme":"mocha", "wallpapers":{}}));
        }
        let mut state: Value = serde_json::from_str(&fs::read_to_string(path)?)?;
        if !state.is_object() || !state["wallpapers"].is_object() {
            bail!("Invalid theme state");
        }
        if state["theme"].is_null() {
            state["theme"] = json!("mocha");
        }
        Ok(state)
    }
    pub fn palette(&self, key: &str) -> Result<&Value> {
        self.palettes
            .get(key)
            .with_context(|| format!("Unknown theme: {key}"))
    }
    pub fn image(&self, state: &Value) -> PathBuf {
        let key = state["theme"].as_str().unwrap_or("mocha");
        let wall = state["wallpapers"][key].as_str().unwrap_or("alpine");
        let image = if self.is_bundled_wallpaper(wall) {
            self.catalog.join(key).join(format!("{wall}.png"))
        } else {
            PathBuf::from(wall)
        };
        if image.is_file() {
            image
        } else {
            self.catalog.join(key).join("alpine.png")
        }
    }
    fn is_bundled_wallpaper(&self, name: &str) -> bool {
        self.wallpapers.iter().any(|(key, _)| key == name)
    }
    pub fn wallpaper(&self, state: &mut Value, path: &str) -> Result<()> {
        let key = state["theme"].as_str().unwrap_or("mocha").to_owned();
        let stored = if self.is_bundled_wallpaper(path) {
            path.to_owned()
        } else {
            let expanded = if let Some(tail) = path.strip_prefix("~/") {
                self.home.join(tail)
            } else {
                PathBuf::from(path)
            };
            let source = expanded
                .canonicalize()
                .context("Wallpaper file does not exist")?;
            let extension = source
                .extension()
                .and_then(|s| s.to_str())
                .unwrap_or("")
                .to_lowercase();
            if !source.is_file() || !["png", "jpg", "jpeg", "webp"].contains(&extension.as_str()) {
                bail!("Choose a PNG, JPEG or WebP image");
            }
            let data = fs::read(&source)?;
            let mut hash = DefaultHasher::new();
            data.hash(&mut hash);
            let dest = self
                .state
                .join("images")
                .join(format!("{:016x}.{extension}", hash.finish()));
            fs::create_dir_all(dest.parent().unwrap())?;
            if !dest.exists() {
                fs::write(&dest, data)?;
            }
            dest.to_string_lossy().into_owned()
        };
        state["wallpapers"][key] = json!(stored);
        Ok(())
    }
    fn gtk(&self, light: bool) -> Result<()> {
        for version in [3, 4] {
            let root = self.config.join(format!("gtk-{version}.0"));
            let css = root.join("gtk.css");
            let text = fs::read_to_string(&css).unwrap_or_default();
            let import = format!(
                "@import url(\"{}\");\n",
                self.current
                    .join(if version == 3 { "gtk.css" } else { "gtk4.css" })
                    .display()
            );
            if !text.contains(&import) {
                backup(&css)?;
                write(&css, &(import + &text))?;
            }
            ini(
                &root.join("settings.ini"),
                "Settings",
                &[
                    (
                        "gtk-theme-name",
                        if light { "Adwaita" } else { "Adwaita-dark" },
                    ),
                    (
                        "gtk-application-prefer-dark-theme",
                        if light { "false" } else { "true" },
                    ),
                ],
            )?;
        }
        for version in [5, 6] {
            ini(
                &self
                    .config
                    .join(format!("qt{version}ct/qt{version}ct.conf")),
                "Appearance",
                &[
                    (
                        "color_scheme_path",
                        &self.current.join("qt.colors").to_string_lossy(),
                    ),
                    ("custom_palette", "true"),
                    ("style", "Fusion"),
                ],
            )?;
        }
        Ok(())
    }
    fn obsidian(&self, light: bool) -> Result<()> {
        let registry = self.config.join("obsidian/obsidian.json");
        if !registry.exists() {
            return Ok(());
        }
        let registry: Value = serde_json::from_str(&fs::read_to_string(registry)?)?;
        if let Some(vaults) = registry["vaults"].as_object() {
            for vault in vaults.values() {
                let Some(path) = vault["path"].as_str() else {
                    continue;
                };
                let root = PathBuf::from(path).join(".obsidian");
                if !root.is_dir() {
                    continue;
                }
                write(
                    &root.join("snippets/dotfiles-theme.css"),
                    &fs::read_to_string(self.current.join("obsidian.css"))?,
                )?;
                let path = root.join("appearance.json");
                let mut prefs: Value = if path.exists() {
                    serde_json::from_str(&fs::read_to_string(&path)?)?
                } else {
                    json!({})
                };
                if prefs["enabledCssSnippets"].is_null() {
                    prefs["enabledCssSnippets"] = json!([]);
                }
                let snippets = prefs["enabledCssSnippets"]
                    .as_array_mut()
                    .context("Invalid Obsidian snippets setting")?;
                if !snippets.iter().any(|s| s == "dotfiles-theme") {
                    snippets.push(json!("dotfiles-theme"));
                }
                prefs["theme"] = json!(if light { "moonstone" } else { "obsidian" });
                backup(&path)?;
                write(&path, &(serde_json::to_string_pretty(&prefs)? + "\n"))?;
            }
        }
        Ok(())
    }
    pub fn apply(&self, state: &Value, save: bool, reload: bool) -> Result<Duration> {
        let start = Instant::now();
        let key = state["theme"].as_str().unwrap_or("mocha");
        let palette = self.palette(key)?;
        let _lock = Lock::new(&self.state.join("lock"), false)?;
        link(&self.catalog.join(key), &self.current)?;
        link(
            &self.current.join("btop.theme"),
            &self.config.join("btop/themes/dotfiles.theme"),
        )?;
        ini(
            &self.config.join("btop/btop.conf"),
            "",
            &[("color_theme", "\"dotfiles\"")],
        )?;
        let light = palette["light"].as_bool().unwrap_or(false);
        if self.desktop {
            link(&self.image(state), &self.state.join("wallpaper"))?;
            if let Err(error) = self.gtk(light).and_then(|_| self.obsidian(light)) {
                eprintln!("Theme app settings: {error:#}");
            }
        }
        if save {
            write(
                &self.state.join("state.json"),
                &(serde_json::to_string_pretty(state)? + "\n"),
            )?;
        }
        if reload {
            notify_editors();
            if self.desktop && std::env::var_os("WAYLAND_DISPLAY").is_some() {
                let signals = signal_app("ghostty", libc::SIGUSR2);
                if std::env::var_os("SYSTEM_THEME_TIMING").is_some() {
                    eprintln!("Ghostty: notified {signals} existing process(es)");
                }
                for (field, value) in [("active", "accent"), ("inactive", "overlay")] {
                    if let Some(hex) = palette[value].as_str().and_then(|s| s.strip_prefix('#')) {
                        let _ = hypr(&format!("keyword general:col.{field}_border rgb({hex})"));
                    }
                }
                signal_app("waybar", libc::SIGUSR2);
                command("makoctl", &["reload"]);
                command(
                    "gsettings",
                    &[
                        "set",
                        "org.gnome.desktop.interface",
                        "color-scheme",
                        if light { "prefer-light" } else { "prefer-dark" },
                    ],
                );
                command(
                    "gsettings",
                    &[
                        "set",
                        "org.gnome.desktop.interface",
                        "gtk-theme",
                        if light { "Adwaita" } else { "Adwaita-dark" },
                    ],
                );
                // Restarting SwayOSD during hover would flicker and interrupt active OSDs.
                // Let systemd wait for shutdown and recover a missing server.
                if save {
                    command("systemctl", &["--user", "restart", "swayosd.service"]);
                }
            }
            command(
                "tmux",
                &[
                    "source-file",
                    &self.current.join("tmux.conf").to_string_lossy(),
                ],
            );
        }
        Ok(start.elapsed())
    }
    pub fn start_wallpaper(&self) {
        if self.desktop && std::env::var_os("WAYLAND_DISPLAY").is_some() {
            command(
                "systemctl",
                &["--user", "start", "desktop-wallpaper.service"],
            );
        }
    }
    pub fn daemon(&self) -> Result<()> {
        let mut last = PathBuf::new();
        let mut child: Option<Child> = None;
        loop {
            let path = self
                .state
                .join("wallpaper")
                .canonicalize()
                .unwrap_or_default();
            if path != last && path.is_file() {
                let mut next = Command::new("swaybg")
                    .args(["-i"])
                    .arg(&path)
                    .args(["-m", "fill"])
                    .spawn()?;
                thread::sleep(Duration::from_millis(80));
                if next.try_wait()?.is_none() {
                    if let Some(mut previous) = child.take() {
                        let _ = previous.kill();
                        let _ = previous.wait();
                    }
                    child = Some(next);
                    last = path;
                }
            }
            if child
                .as_mut()
                .is_some_and(|c| c.try_wait().ok().flatten().is_some())
            {
                last.clear();
            }
            thread::sleep(Duration::from_millis(40));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn nix_wrapped_process_names_are_recognized_without_matching_arguments() {
        assert!(executable_matches(
            Path::new("/nix/store/hash-ghostty/bin/.ghostty-wrapped"),
            "ghostty"
        ));
        assert!(executable_matches(Path::new("/usr/bin/ghostty"), "ghostty"));
        assert!(!executable_matches(Path::new("/usr/bin/pgrep"), "ghostty"));
        assert!(!executable_matches(
            Path::new("/tmp/ghostty-helper"),
            "ghostty"
        ));
    }
}
