mod model;
mod render;
mod wayland;
use anyhow::{bail, Context, Result};
use std::{
    io::{Read, Write},
    os::unix::net::UnixStream,
    path::PathBuf,
    process::Command,
    time::Duration,
};
fn socket() -> Result<PathBuf> {
    Ok(
        PathBuf::from(std::env::var_os("XDG_RUNTIME_DIR").context("Missing XDG_RUNTIME_DIR")?)
            .join("desktop-which-key.sock"),
    )
}
fn send(request: &str) -> Result<String> {
    let mut stream = UnixStream::connect(socket()?)?;
    stream.set_read_timeout(Some(Duration::from_secs(3)))?;
    stream.set_write_timeout(Some(Duration::from_secs(1)))?;
    stream.write_all(request.as_bytes())?;
    stream.shutdown(std::net::Shutdown::Write)?;
    let mut reply = String::new();
    stream.read_to_string(&mut reply)?;
    if reply.starts_with("error:") {
        bail!("{}", reply.trim());
    }
    Ok(reply)
}
fn run() -> Result<()> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    match args.first().map(String::as_str).unwrap_or("toggle") {
        "--daemon" => return wayland::run(socket()?),
        "--list" => {
            println!("{}", serde_json::to_string_pretty(&model::load()?)?);
            return Ok(());
        }
        "--check" => {
            let bindings = model::load()?;
            model::validate(&bindings)?;
            println!("Validated {} bindings: no collisions, at most two modifiers, every group cancellable",bindings.len());
            return Ok(());
        }
        _ => {}
    }
    let request = if args.is_empty() {
        "toggle".into()
    } else {
        args.join(" ")
    };
    if ["toggle", "show", "search"].contains(&args.first().map(String::as_str).unwrap_or("toggle"))
    {
        Command::new("hyprctl")
            .args(["dispatch", "submap", "reset"])
            .output()?;
    }
    let reply = match send(&request) {
        Ok(reply) => reply,
        Err(e) if ["hold-end", "end-context", "hide"].contains(&request.as_str()) => {
            eprintln!("desktop-which-key: {e:#}");
            return Ok(());
        }
        Err(_) => {
            Command::new("systemctl")
                .args(["--user", "start", "keybind-hints.service"])
                .status()?;
            let mut answer = None;
            for _ in 0..20 {
                if let Ok(reply) = send(&request) {
                    answer = Some(reply);
                    break;
                }
                std::thread::sleep(Duration::from_millis(25));
            }
            answer.context("Which-key service unavailable")?
        }
    };
    print!("{reply}");
    Ok(())
}
fn main() {
    if let Err(e) = run() {
        eprintln!("desktop-which-key: {e:#}");
        std::process::exit(1);
    }
}
