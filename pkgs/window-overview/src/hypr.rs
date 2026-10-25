use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use std::{
    io::{Read, Write},
    os::unix::net::UnixStream,
    path::PathBuf,
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

#[derive(Clone, Debug, Serialize)]
pub struct Snapshot {
    pub monitors: Vec<Monitor>,
    pub workspaces: Vec<Workspace>,
    pub clients: Vec<Client>,
    pub monitor: String,
    pub active_address: String,
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

pub fn dispatch(action: &str, argument: &str) -> Result<()> {
    let answer = request(&format!("dispatch {action} {argument}"))?;
    if answer.trim() != "ok" {
        bail!("{action}: {}", answer.trim());
    }
    Ok(())
}

pub fn snapshot(target: Option<&str>) -> Result<Snapshot> {
    let monitors: Vec<Monitor> = serde_json::from_str(&request("j/monitors")?)?;
    let monitor = target
        .map(str::to_owned)
        .or_else(|| monitors.iter().find(|m| m.focused).map(|m| m.name.clone()))
        .context("No focused monitor")?;
    if !monitors.iter().any(|m| m.name == monitor) {
        bail!("Monitor {monitor} is disconnected");
    }
    let mut workspaces: Vec<Workspace> = serde_json::from_str(&request("j/workspaces")?)?;
    workspaces.retain(|w| !w.name.starts_with("set:"));
    workspaces.sort_by_key(|w| (w.name.parse::<u32>().unwrap_or(u32::MAX), w.name.clone()));
    let mut clients: Vec<Client> = serde_json::from_str(&request("j/clients")?)?;
    clients.retain(|c| c.mapped && c.class != "window-overview" && !c.workspace.name.starts_with("set:"));
    // Spatial order is independent of focus history, so left never becomes right.
    clients.sort_by_key(|c| {
        (
            c.workspace.name.parse::<u32>().unwrap_or(u32::MAX),
            c.workspace.name.clone(),
            c.at[1],
            c.at[0],
            c.address.clone(),
        )
    });
    let active: serde_json::Value = serde_json::from_str(&request("j/activewindow")?)?;
    Ok(Snapshot {
        monitors,
        workspaces,
        clients,
        monitor,
        active_address: active["address"].as_str().unwrap_or("").to_owned(),
    })
}

pub fn selector(workspace: &Workspace) -> String {
    if workspace.id > 0 && workspace.name == workspace.id.to_string() {
        workspace.name.clone()
    } else {
        format!("name:{}", workspace.name)
    }
}

pub fn focus_workspace(workspace: &Workspace, monitor: &str) -> Result<()> {
    let monitors: Vec<Monitor> = serde_json::from_str(&request("j/monitors")?)?;
    let target = monitors
        .iter()
        .find(|m| m.name == monitor)
        .context("Destination monitor disconnected")?;
    dispatch("focusmonitor", monitor)?;
    if workspace.name == "special" || workspace.name.starts_with("special:") {
        if target.special_workspace.id != workspace.id {
            dispatch(
                "togglespecialworkspace",
                workspace.name.strip_prefix("special:").unwrap_or(""),
            )?;
        }
    } else {
        dispatch("focusworkspaceoncurrentmonitor", &selector(workspace))?;
    }
    Ok(())
}

pub fn focus(address: &str, monitor: &str) -> Result<()> {
    let clients: Vec<Client> = serde_json::from_str(&request("j/clients")?)?;
    let client = clients
        .iter()
        .find(|c| c.address == address && c.mapped)
        .context("That window has closed")?;
    focus_workspace(&client.workspace, monitor)?;
    dispatch("focuswindow", &format!("address:{address}"))
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
    fn named_and_numeric_workspace_selectors() {
        assert_eq!(
            selector(&Workspace {
                id: 5,
                name: "5".into(),
                monitor: String::new()
            }),
            "5"
        );
        assert_eq!(
            selector(&Workspace {
                id: 5,
                name: "code".into(),
                monitor: String::new()
            }),
            "name:code"
        );
    }
}
