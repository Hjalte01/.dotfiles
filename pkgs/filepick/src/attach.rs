use crate::{clipboard::Offer, transfer};
use anyhow::{bail, Context, Result};
use serde_json::Value;
use std::{
    path::PathBuf,
    process::Command,
    thread,
    time::{Duration, Instant},
};

/// The browser window recorded before the picker takes keyboard focus.
pub struct Destination {
    address: String,
    class: String,
    pid: u64,
}

impl Destination {
    pub fn parse(json: &str) -> Result<Option<Self>> {
        let window: Value = serde_json::from_str(json).context("Invalid destination window")?;
        let class = window["class"].as_str().unwrap_or_default();
        let lower = class.to_ascii_lowercase();
        if !lower.contains("firefox") && !lower.contains("librewolf") {
            return Ok(None);
        }
        let address = window["address"].as_str().unwrap_or_default();
        if !address.strip_prefix("0x").is_some_and(|digits| {
            !digits.is_empty() && digits.bytes().all(|byte| byte.is_ascii_hexdigit())
        }) {
            bail!("Missing or invalid Firefox window address");
        }
        let pid = window["pid"].as_u64().filter(|pid| *pid > 0);
        Ok(Some(Self {
            address: address.to_owned(),
            class: class.to_owned(),
            pid: pid.context("Missing Firefox process ID")?,
        }))
    }

    fn matches(&self, window: &Value) -> bool {
        window["address"].as_str() == Some(self.address.as_str())
            && window["class"].as_str() == Some(self.class.as_str())
            && window["pid"].as_u64() == Some(self.pid)
    }

    fn selector(&self) -> String {
        format!("address:{}", self.address)
    }

    fn focus(&self) -> Result<()> {
        let clients = hypr_json("clients")?;
        if !clients
            .as_array()
            .is_some_and(|windows| windows.iter().any(|window| self.matches(window)))
        {
            bail!("The original Firefox window has closed");
        }
        dispatch("focuswindow", &self.selector())?;
        // Let Firefox restore its existing focused input and finish the picker
        // key release before sending the first paste. Do not click the page:
        // doing so would replace the input the user chose before opening us.
        thread::sleep(Duration::from_millis(120));
        self.ensure_focused()
    }

    fn ensure_focused(&self) -> Result<()> {
        if !self.matches(&hypr_json("activewindow")?) {
            bail!("Firefox lost focus; stopped attaching files");
        }
        Ok(())
    }
}

fn hypr_json(command: &str) -> Result<Value> {
    let output = Command::new("hyprctl").args(["-j", command]).output()?;
    if !output.status.success() {
        bail!("Could not read Hyprland {command}");
    }
    serde_json::from_slice(&output.stdout).context("Could not read Hyprland window information")
}

fn dispatch(command: &str, argument: &str) -> Result<()> {
    let output = Command::new("hyprctl")
        .args(["dispatch", command, argument])
        .output()?;
    if !output.status.success() || output.stdout.trim_ascii() != b"ok" {
        bail!(
            "Hyprland could not {command}: {}",
            String::from_utf8_lossy(&output.stdout).trim()
        );
    }
    Ok(())
}

/// Firefox's Linux clipboard exposes one file per paste. Publish and paste each
/// file separately into the preserved input, then leave the complete selection
/// on the clipboard for manual reuse. Only Ctrl+V is sent, never Enter/submit.
pub fn paste(files: &[PathBuf], destination: &Destination) -> Result<()> {
    let mut sent = 0;
    let mut offer = None;
    let result: Result<()> = (|| {
        destination.focus()?;
        for file in files {
            destination.ensure_focused()?;
            offer = Some(Offer::publish(file)?);
            destination.ensure_focused()?;
            dispatch(
                "sendshortcut",
                &format!("CTRL,V,{}", destination.selector()),
            )?;
            let deadline = Instant::now() + Duration::from_secs(10);
            while !offer
                .as_ref()
                .unwrap()
                .was_read(Duration::from_millis(25))?
            {
                destination.ensure_focused()?;
                if Instant::now() >= deadline {
                    bail!("Firefox did not read the file paste; use d to drag into this site");
                }
            }
            sent += 1;
            // The actual URI has been consumed, even if the browser was busy.
            // Let GTK finish the paste before issuing another shortcut.
            thread::sleep(Duration::from_millis(80));
        }
        Ok(())
    })();
    let restore = transfer::copy(files, false);
    result.with_context(|| {
        format!(
            "Sent {sent}/{} files. Super+Alt+D opens the saved selection for dragging",
            files.len()
        )
    })?;
    restore
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn automatic_pasting_requires_a_specific_firefox_window() {
        for class in ["firefox", "org.mozilla.Firefox", "LibreWolf"] {
            let window = json!({"address": "0xab123", "class": class, "pid": 123});
            assert!(Destination::parse(&window.to_string()).unwrap().is_some());
        }
        for class in ["", "org.gnome.Nautilus", "com.mitchellh.ghostty"] {
            assert!(Destination::parse(&json!({"class": class}).to_string())
                .unwrap()
                .is_none());
        }
        for window in [
            json!({"class": "firefox", "pid": 123}),
            json!({"class": "firefox", "address": "0x" , "pid": 123}),
            json!({"class": "firefox", "address": "0x12,activewindow", "pid": 123}),
            json!({"class": "firefox", "address": "0x12", "pid": 0}),
            json!({"class": "firefox", "address": "0x12"}),
        ] {
            assert!(Destination::parse(&window.to_string()).is_err());
        }
    }

    #[test]
    fn focus_guard_rejects_another_window_or_reused_address() {
        let window = json!({"address": "0xab123", "class": "firefox", "pid": 123});
        let destination = Destination::parse(&window.to_string()).unwrap().unwrap();
        assert!(destination.matches(&window));
        for replacement in [
            json!({"address": "0xab124", "class": "firefox", "pid": 123}),
            json!({"address": "0xab123", "class": "firefox", "pid": 124}),
            json!({"address": "0xab123", "class": "another-app", "pid": 123}),
            json!({}),
        ] {
            assert!(!destination.matches(&replacement));
        }
    }
}
