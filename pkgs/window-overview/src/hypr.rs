use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use std::{
    collections::BTreeMap,
    fs::{self, OpenOptions},
    io::{Read, Write},
    os::fd::AsRawFd,
    os::unix::net::UnixStream,
    path::PathBuf,
    process::Command,
    time::Duration,
};

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct Workspace {
    pub id: i64,
    pub name: String,
    #[serde(default)]
    pub monitor: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Monitor {
    pub id: i64,
    pub name: String,
    pub width: u32,
    pub height: u32,
    pub x: i32,
    pub y: i32,
    pub scale: f64,
    #[serde(default)]
    pub transform: u32,
    pub focused: bool,
    pub active_workspace: Workspace,
    pub special_workspace: Workspace,
}
impl Monitor {
    pub fn logical_size(&self) -> [f32; 2] {
        let (w, h) = if self.transform % 2 == 1 {
            (self.height, self.width)
        } else {
            (self.width, self.height)
        };
        [w as f32 / self.scale as f32, h as f32 / self.scale as f32]
    }
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Client {
    pub address: String,
    pub mapped: bool,
    pub at: [i32; 2],
    pub size: [i32; 2],
    pub workspace: Workspace,
    pub monitor: i64,
    pub class: String,
    pub title: String,
    #[serde(default)]
    pub fullscreen: u32,
    #[serde(default, rename = "fullscreenClient")]
    pub fullscreen_client: u32,
    #[serde(default)]
    pub floating: bool,
    #[serde(default)]
    pub grouped: Vec<String>,
}
impl Client {
    pub fn app(&self) -> &str {
        match self.class.as_str() {
            "com.mitchellh.ghostty" => "Ghostty",
            "firefox" => "Firefox",
            "obsidian" => "Obsidian",
            other => other,
        }
    }
    pub fn states(&self) -> String {
        let mut states = Vec::new();
        if self.fullscreen == 2 {
            states.push("FULLSCREEN");
        } else if self.fullscreen == 1 {
            states.push("MAXIMIZED");
        } else if self.fullscreen_client == 2 {
            states.push("APP FULLSCREEN");
        }
        if self.floating {
            states.push("FLOATING");
        }
        if !self.grouped.is_empty() {
            states.push("GROUPED TAB");
        }
        states.join(" · ")
    }
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct WorkspaceSet {
    #[serde(default)]
    pub id: String,
    pub name: String,
    #[serde(default)]
    pub monitors: BTreeMap<String, String>,
}
#[derive(Deserialize)]
struct SetState {
    current: String,
    sets: BTreeMap<String, WorkspaceSet>,
    session: Option<String>,
}

// A parked workspace keeps its ID; only its name changes during a set switch.
pub fn parked(name: &str) -> Option<(&str, &str)> {
    let (set, slot) = name.strip_prefix("set:")?.rsplit_once(':')?;
    (is_slot(slot) && !set.is_empty()).then_some((set, slot))
}
pub fn is_slot(name: &str) -> bool {
    matches!(name, "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9")
}
pub fn workspace_label(name: &str) -> &str {
    parked(name).map(|(_, slot)| slot).unwrap_or(name)
}

#[derive(Clone, Debug, Serialize)]
pub struct Snapshot {
    pub monitors: Vec<Monitor>,
    pub workspaces: Vec<Workspace>,
    pub clients: Vec<Client>,
    pub monitor: String,
    pub active_address: String,
    pub current_set: String,
    pub sets: Vec<WorkspaceSet>,
}

impl Snapshot {
    pub fn workspace_set<'a>(&'a self, name: &'a str) -> Option<&'a str> {
        parked(name)
            .map(|(set, _)| set)
            .or_else(|| is_slot(name).then_some(self.current_set.as_str()))
    }
    pub fn set_name<'a>(&'a self, id: &'a str) -> &'a str {
        self.sets
            .iter()
            .find(|s| s.id == id)
            .map(|s| s.name.as_str())
            .unwrap_or(id)
    }
    pub fn context(&self, workspace: &Workspace) -> String {
        let set = self
            .workspace_set(&workspace.name)
            .map(|id| self.set_name(id))
            .unwrap_or("Shared");
        format!("{} · Workspace {}", set, workspace_label(&workspace.name))
    }
}

fn socket() -> Result<PathBuf> {
    Ok(PathBuf::from(std::env::var("XDG_RUNTIME_DIR")?)
        .join("hypr")
        .join(std::env::var("HYPRLAND_INSTANCE_SIGNATURE")?)
        .join(".socket.sock"))
}

pub fn request(command: &str) -> Result<String> {
    let mut connection = UnixStream::connect(socket()?).context("connect to Hyprland")?;
    connection.set_read_timeout(Some(Duration::from_secs(3)))?;
    connection.set_write_timeout(Some(Duration::from_secs(3)))?;
    connection.write_all(command.as_bytes())?;
    let mut response = String::new();
    connection.read_to_string(&mut response)?;
    Ok(response)
}

pub fn snapshot(target: Option<&str>) -> Result<Snapshot> {
    // Use the same lock as workspace-set: never mix pre/post-rename snapshots.
    let state_dir = std::env::var_os("XDG_STATE_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            PathBuf::from(std::env::var_os("HOME").unwrap_or_default()).join(".local/state")
        })
        .join("workspace-sets");
    fs::create_dir_all(&state_dir)?;
    let lock = OpenOptions::new()
        .create(true)
        .truncate(false)
        .write(true)
        .open(state_dir.join("state.lock"))?;
    if unsafe { libc::flock(lock.as_raw_fd(), libc::LOCK_SH) } != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    let state = fs::read_to_string(state_dir.join("state.json"))
        .ok()
        .and_then(|data| serde_json::from_str::<SetState>(&data).ok());
    let (current_set, mut sets) = if let Some(state) = state {
        let same_session = state.session.as_deref()
            == std::env::var("HYPRLAND_INSTANCE_SIGNATURE").ok().as_deref();
        let sets = state
            .sets
            .into_iter()
            .map(|(id, mut set)| {
                set.id = id;
                if !same_session {
                    set.monitors.clear();
                }
                set
            })
            .collect::<Vec<_>>();
        (state.current, sets)
    } else {
        (
            "current".to_owned(),
            ["Current", "School", "Hobbies", "Fun"]
                .into_iter()
                .map(|name| WorkspaceSet {
                    id: name.to_lowercase(),
                    name: name.into(),
                    monitors: BTreeMap::new(),
                })
                .collect(),
        )
    };
    sets.sort_by_key(|s| (s.id != current_set, s.name.to_lowercase()));
    let monitors: Vec<Monitor> = serde_json::from_str(&request("j/monitors")?)?;
    let monitor = target
        .map(str::to_owned)
        .or_else(|| monitors.iter().find(|m| m.focused).map(|m| m.name.clone()))
        .context("No focused monitor")?;
    if !monitors.iter().any(|m| m.name == monitor) {
        bail!("Monitor {monitor} is disconnected");
    }
    let mut workspaces: Vec<Workspace> = serde_json::from_str(&request("j/workspaces")?)?;
    workspaces.sort_by_key(|w| (w.name.parse::<u32>().unwrap_or(u32::MAX), w.name.clone()));
    let mut clients: Vec<Client> = serde_json::from_str(&request("j/clients")?)?;
    clients.retain(|c| c.mapped && c.class != "window-overview");
    // Spatial order is independent of focus history, so left never becomes right.
    clients.sort_by_key(|c| {
        (
            parked(&c.workspace.name).is_some(),
            parked(&c.workspace.name)
                .map(|(id, _)| id)
                .unwrap_or("")
                .to_owned(),
            workspace_label(&c.workspace.name)
                .parse::<u32>()
                .unwrap_or(u32::MAX),
            c.workspace.name.clone(),
            c.at[1],
            c.at[0],
            c.address.clone(),
        )
    });
    let active: serde_json::Value = serde_json::from_str(&request("j/activewindow")?)?;
    Ok(Snapshot {
        current_set,
        sets,
        monitors,
        workspaces,
        clients,
        monitor,
        active_address: active["address"].as_str().unwrap_or("").to_owned(),
    })
}

pub fn focus(address: &str, monitor: &str) -> Result<()> {
    let helper = PathBuf::from(std::env::var("HOME")?).join(".local/bin/workspace-set");
    let result = Command::new(helper)
        .args(["focus-window", address, monitor])
        .output()?;
    if !result.status.success() {
        bail!("{}", String::from_utf8_lossy(&result.stderr).trim());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn monitor_rotation_and_scale() {
        let m = Monitor {
            id: 0,
            name: "test".into(),
            width: 3840,
            height: 2160,
            x: -1920,
            y: 0,
            scale: 2.,
            transform: 1,
            focused: true,
            active_workspace: Workspace::default(),
            special_workspace: Workspace::default(),
        };
        assert_eq!(m.logical_size(), [1080., 1920.]);
    }
    #[test]
    fn parked_names_only_accept_workspace_set_slots() {
        assert_eq!(parked("set:school:5"), Some(("school", "5")));
        assert_eq!(parked("set:school:10"), None);
        assert_eq!(parked("special:school"), None);
        assert_eq!(parked("set::1"), None);
        assert_eq!(workspace_label("set:school:5"), "5");
    }
}
