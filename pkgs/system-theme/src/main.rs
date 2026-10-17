mod engine;
#[cfg(feature = "desktop")]
mod picker;
use anyhow::{bail, Result};
use engine::Engine;
use serde_json::json;

fn main() {
    if let Err(error) = run() {
        eprintln!("Theme: {error:#}");
        std::process::exit(1);
    }
}
fn run() -> Result<()> {
    let mut args: Vec<String> = std::env::args().skip(1).collect();
    let reload = !args.iter().any(|arg| arg == "--no-reload");
    args.retain(|arg| arg != "--no-reload");
    let action = args.first().map(String::as_str).unwrap_or("menu");
    if ["--help", "-h"].contains(&action) {
        println!("system-theme [menu|set NAME|next|wallpaper [FILE]|wallpaper-next|apply|preview NAME|cancel|status|list] [--no-reload]");
        return Ok(());
    }
    let engine = Engine::new()?;
    if action == "wallpaper-daemon" {
        return engine.daemon();
    }
    let mut state = engine.saved()?;
    match action {
        "status" => {
            println!("{}", serde_json::to_string_pretty(&state)?);
            return Ok(());
        }
        "list" => {
            for key in engine.keys() {
                println!(
                    "{key}\t{}",
                    engine.palette(&key)?["name"].as_str().unwrap_or(&key)
                );
            }
            return Ok(());
        }
        "menu" | "wallpaper" if action == "menu" || args.len() == 1 => {
            if !engine.desktop {
                bail!("Use `system-theme set NAME` on this host");
            }
            #[cfg(feature = "desktop")]
            return picker::run(engine, action == "wallpaper");
            #[cfg(not(feature = "desktop"))]
            bail!("This build does not include the desktop picker");
        }
        "set" | "preview" => {
            let key = args
                .get(1)
                .ok_or_else(|| anyhow::anyhow!("Choose a theme from `system-theme list`"))?;
            engine.palette(key)?;
            state["theme"] = json!(key);
        }
        "next" => {
            let keys = engine.keys();
            let current = keys
                .iter()
                .position(|key| state["theme"] == *key)
                .unwrap_or(0);
            state["theme"] = json!(keys[(current + 1) % keys.len()]);
        }
        "wallpaper" => {
            engine.wallpaper(&mut state, args.get(1).unwrap())?;
        }
        "wallpaper-next" => {
            let key = state["theme"].as_str().unwrap_or("mocha");
            let walls = &engine.wallpapers;
            let current = walls
                .iter()
                .position(|(wall, _)| state["wallpapers"][key].as_str().unwrap_or("alpine") == wall)
                .unwrap_or(walls.len() - 1);
            engine.wallpaper(&mut state, &walls[(current + 1) % walls.len()].0)?;
        }
        "apply" | "cancel" => {}
        _ => bail!("Unknown action: {action}. Run system-theme --help"),
    }
    let elapsed = engine.apply(&state, action != "preview", reload)?;
    if reload {
        engine.start_wallpaper();
    }
    if std::env::var_os("SYSTEM_THEME_TIMING").is_some() {
        eprintln!("Theme switched in {:.1} ms", elapsed.as_secs_f64() * 1000.);
    }
    Ok(())
}
