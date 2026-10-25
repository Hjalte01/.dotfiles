use std::env;
use std::fs::{self, OpenOptions};
use std::io::{self, Read, Write};
use std::os::unix::fs::OpenOptionsExt;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::thread;
use std::time::Duration;

mod history;

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

use dictation::{Rule, load_rules, normalize};

fn require_success(command: &mut Command) -> Result<()> {
    let status = command.status()?;
    if !status.success() {
        return Err(format!("{command:?} failed with {status}").into());
    }
    Ok(())
}

enum Clipboard {
    Empty,
    Data { mime: String, bytes: Vec<u8> },
}

impl Clipboard {
    fn capture() -> Result<Self> {
        let types = Command::new("wl-paste").arg("--list-types").output()?;
        if !types.status.success() {
            return Ok(Self::Empty);
        }
        let types = String::from_utf8(types.stdout)?;
        let available: Vec<&str> = types.lines().filter(|mime| !mime.is_empty()).collect();
        let mime = [
            "text/plain;charset=utf-8",
            "text/plain",
            "image/png",
            "image/jpeg",
        ]
        .iter()
        .find(|mime| available.contains(mime))
        .copied()
        .or_else(|| {
            available
                .iter()
                .copied()
                .find(|mime| mime.starts_with("text/") || mime.starts_with("image/"))
        })
        .or_else(|| available.first().copied());
        let Some(mime) = mime else {
            return Ok(Self::Empty);
        };
        let data = Command::new("wl-paste")
            .args(["--no-newline", "--type", mime])
            .output()?;
        if !data.status.success() {
            return Err("Could not save the current clipboard".into());
        }
        Ok(Self::Data {
            mime: mime.to_string(),
            bytes: data.stdout,
        })
    }

    fn restore(&self) -> Result<()> {
        match self {
            Self::Empty => require_success(Command::new("wl-copy").arg("--clear")),
            Self::Data { mime, bytes } => copy_to_clipboard(mime, bytes),
        }
    }
}

fn copy_to_clipboard(mime: &str, bytes: &[u8]) -> Result<()> {
    // wl-copy forks a clipboard owner; inherited pipes must not keep Handy waiting.
    let mut clipboard = Command::new("wl-copy")
        .args(["--type", mime])
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()?;
    let write_result = clipboard
        .stdin
        .take()
        .ok_or("Missing clipboard stdin")?
        .write_all(bytes);
    let status = clipboard.wait()?;
    write_result?;
    if !status.success() {
        return Err(format!("wl-copy failed with {status}").into());
    }
    Ok(())
}

fn paste(text: &str, rules: &[Rule]) -> Result<()> {
    let recognized = text;
    let text = normalize(text, rules);
    if text.trim().is_empty() {
        return Ok(());
    }
    let original = Clipboard::capture()?;
    if let Err(error) = copy_to_clipboard("text/plain;charset=utf-8", text.as_bytes()) {
        let _ = original.restore();
        return Err(error);
    }
    thread::sleep(Duration::from_millis(60));
    let pasted = require_success(Command::new("wtype").args([
        "-M", "ctrl", "-M", "shift", "-P", "v", "-p", "v", "-m", "shift", "-m", "ctrl",
    ]));
    // Match Handy's original delay so the target can read before restoration.
    thread::sleep(Duration::from_millis(60));
    let restored = original.restore();
    if pasted.is_ok() {
        history::record(recognized, &text);
    }
    pasted.and(restored)
}

fn notify(summary: &str, body: &str, timeout: &str) {
    let _ = Command::new("notify-send")
        .args([
            "--app-name=Dictation",
            "--hint=string:x-canonical-private-synchronous:handy-dictation",
            "--expire-time",
            timeout,
            summary,
            body,
        ])
        .status();
}

fn toggle() -> Result<()> {
    let runtime = PathBuf::from(env::var_os("XDG_RUNTIME_DIR").ok_or("XDG_RUNTIME_DIR is unset")?);
    let live_socket = runtime.join("dictation-live/control.sock");
    if live_socket.exists() {
        use std::os::unix::net::UnixStream;
        let mut connection = UnixStream::connect(live_socket)?;
        connection.set_read_timeout(Some(Duration::from_secs(2)))?;
        connection.write_all(b"toggle\n")?;
        let mut response = String::new();
        io::BufRead::read_line(&mut io::BufReader::new(connection), &mut response)?;
        if response.trim() != "ok" {
            return Err(response.trim().to_owned().into());
        }
        return Ok(());
    }
    let lock = OpenOptions::new()
        .create(true)
        .truncate(false)
        .write(true)
        .mode(0o600)
        .open(runtime.join("dictation-toggle.lock"))?;
    lock.lock()?;
    let marker = runtime.join("handy-recording");
    let service = Command::new("systemctl")
        .args([
            "--user",
            "show",
            "handy.service",
            "--property=MainPID",
            "--value",
        ])
        .output()?;
    let pid: u32 = String::from_utf8(service.stdout)?
        .trim()
        .parse()
        .unwrap_or(0);
    if !service.status.success() || pid == 0 {
        let _ = fs::remove_file(&marker);
        notify("Dictation unavailable", "Handy is not running.", "4000");
        return Err("Handy is not running".into());
    }
    let stat = fs::read_to_string(format!("/proc/{pid}/stat"))?;
    let start = stat
        .rsplit_once(')')
        .and_then(|(_, rest)| rest.split_whitespace().nth(19))
        .ok_or("Cannot read Handy process start time")?;
    let identity = format!("{pid}:{start}");
    let was_recording = fs::read_to_string(&marker).is_ok_and(|value| value == identity);
    require_success(Command::new("systemctl").args([
        "--user",
        "kill",
        "--signal=SIGUSR2",
        "--kill-whom=main",
        "handy.service",
    ]))?;
    if was_recording {
        fs::remove_file(marker)?;
        notify(
            "Dictation stopped",
            "Transcribing and inserting text…",
            "2500",
        );
    } else {
        let mut file = OpenOptions::new()
            .create(true)
            .truncate(true)
            .write(true)
            .mode(0o600)
            .open(marker)?;
        file.write_all(identity.as_bytes())?;
        notify(
            "🎙 Dictation is ON",
            "Press F11 or Super+D to stop and insert text.",
            "0",
        );
    }
    Ok(())
}

fn input(arguments: &[String]) -> Result<String> {
    match arguments {
        [] => {
            let mut text = String::new();
            io::stdin().read_to_string(&mut text)?;
            Ok(text)
        }
        [text] => Ok(text.clone()),
        _ => Err("Pass the transcript as one argument, or through stdin".into()),
    }
}

fn run() -> Result<()> {
    let mut args = env::args().skip(1);
    let command = args.next().unwrap_or_else(|| "help".to_string());
    let arguments: Vec<String> = args.collect();
    match command.as_str() {
        "normalize" => {
            let text = normalize(&input(&arguments)?, &load_rules()?);
            io::stdout().write_all(text.as_bytes())?;
            Ok(())
        }
        "paste" => paste(&input(&arguments)?, &load_rules()?),
        "toggle" if arguments.is_empty() => toggle(),
        "history" => {
            let history = history::History::configured()?;
            match arguments.as_slice() {
                [argument] if argument == "path" => println!("{}", history.path().display()),
                [argument] if argument == "clear" => {
                    history.clear()?;
                    println!("Dictation history cleared.");
                }
                [] => {
                    for record in history.recent(20)? {
                        println!("{record}");
                    }
                }
                [count] => {
                    for record in history.recent(count.parse()?)? {
                        println!("{record}");
                    }
                }
                _ => return Err("Use: dictation history [COUNT|path|clear]".into()),
            }
            Ok(())
        }
        "help" | "--help" | "-h" => {
            println!(
                "dictation normalize [TEXT]   Correct notation (or read stdin)\ndictation paste [TEXT]       Correct notation and paste on Wayland\ndictation toggle             Toggle live dictation (Handy fallback)\ndictation history [COUNT]    Show recent raw/corrected transcripts (default 20)\ndictation history path       Print the local cache path\ndictation history clear      Clear the transcript cache\n\nDictionary: $DICTATION_TERMS or ~/.config/dictation/terms.tsv\nCache: $DICTATION_CACHE_DIR or ~/.cache/dictation\nSet DICTATION_HISTORY=0 to disable caching."
            );
            Ok(())
        }
        _ => Err(format!("Unknown command: {command}").into()),
    }
}

fn main() {
    if let Err(error) = run() {
        eprintln!("dictation: {error}");
        std::process::exit(1);
    }
}
