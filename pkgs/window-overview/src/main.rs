mod hypr;
mod layout;
mod render;
mod wayland;

use anyhow::{Context, Result};
use std::{
    io::{Read, Write},
    os::unix::net::UnixStream,
    path::PathBuf,
    process::Command,
    time::Duration,
};

fn socket() -> Result<PathBuf> {
    Ok(PathBuf::from(std::env::var("XDG_RUNTIME_DIR")?).join("window-overview-rust.sock"))
}
fn send(command: &str) -> Result<String> {
    let mut stream = UnixStream::connect(socket()?)?;
    stream.set_read_timeout(Some(Duration::from_secs(5)))?;
    stream.write_all(command.as_bytes())?;
    stream.shutdown(std::net::Shutdown::Write)?;
    let mut response = String::new();
    stream.read_to_string(&mut response)?;
    Ok(response)
}

fn main() {
    if let Err(error) = run() {
        eprintln!("window-overview: {error:#}");
        std::process::exit(1);
    }
}
fn run() -> Result<()> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let command = args.first().map(String::as_str).unwrap_or("toggle");
    if ["--list", "--snapshot"].contains(&command) {
        println!("{}", serde_json::to_string_pretty(&hypr::snapshot(None)?)?);
        return Ok(());
    }
    if command == "--activate" {
        let entry: serde_json::Value =
            serde_json::from_str(args.get(1).context("Missing activation JSON")?)?;
        let target = args
            .windows(2)
            .find(|a| a[0] == "--monitor")
            .map(|a| a[1].clone())
            .unwrap_or(hypr::snapshot(None)?.monitor);
        hypr::focus(
            entry["address"].as_str().context("Missing address")?,
            &target,
        )?;
        return Ok(());
    }
    if command == "--daemon" {
        return wayland::run(socket()?);
    }
    let request = if command == "--search" {
        "search".to_owned()
    } else {
        args.join(" ")
    };
    let request = if request.is_empty() {
        "toggle"
    } else {
        &request
    };
    match send(request) {
        Ok(answer) => print!("{answer}"),
        Err(_) if ["toggle", "open", "search"].contains(&request) => {
            Command::new("systemctl")
                .args(["--user", "start", "window-overview.service"])
                .status()?;
            let mut answer = None;
            for _ in 0..30 {
                if let Ok(value) = send(request) {
                    answer = Some(value);
                    break;
                }
                std::thread::sleep(Duration::from_millis(50));
            }
            print!("{}", answer.context("Overview service did not start")?);
        }
        Err(error) => return Err(error),
    }
    Ok(())
}
