mod audio;
mod pipeline;
mod recognizer;
mod ui;

use anyhow::{Context, Result, bail};
use pipeline::{Shared, lock};
use std::{
    env,
    fs::{self, OpenOptions},
    io::{BufRead, BufReader, Read, Write},
    os::unix::{
        fs::{OpenOptionsExt, PermissionsExt},
        net::{UnixListener, UnixStream},
    },
    path::{Path, PathBuf},
    sync::{Arc, mpsc},
    thread,
    time::{Duration, Instant},
};

fn runtime() -> Result<PathBuf> {
    Ok(
        PathBuf::from(env::var_os("XDG_RUNTIME_DIR").context("XDG_RUNTIME_DIR is unset")?)
            .join("dictation-live"),
    )
}

fn request(command: &str) -> Result<()> {
    let path = runtime()?.join("control.sock");
    let mut stream = UnixStream::connect(&path)
        .with_context(|| format!("Dictation is not running ({})", path.display()))?;
    stream.set_read_timeout(Some(Duration::from_secs(2)))?;
    stream.write_all(format!("{command}\n").as_bytes())?;
    let mut answer = String::new();
    BufReader::new(stream).take(256).read_line(&mut answer)?;
    if command == "status" {
        print!("{answer}");
    } else if answer.trim() != "ok" {
        bail!("{}", answer.trim());
    }
    Ok(())
}

fn serve() -> Result<()> {
    let root = runtime()?;
    fs::create_dir_all(&root)?;
    fs::set_permissions(&root, fs::Permissions::from_mode(0o700))?;
    let guard = OpenOptions::new()
        .create(true)
        .truncate(false)
        .write(true)
        .mode(0o600)
        .open(root.join("service.lock"))?;
    guard
        .try_lock()
        .context("Another dictation service is already running")?;
    let path = root.join("control.sock");
    if path.exists() {
        fs::remove_file(&path)?;
    }
    let listener = UnixListener::bind(&path)?;
    fs::set_permissions(&path, fs::Permissions::from_mode(0o600))?;
    let shared = Shared::new();
    let (send, receive) = mpsc::channel();
    let control_view = Arc::clone(&shared);
    thread::spawn(move || {
        for stream in listener.incoming() {
            let Ok(mut stream) = stream else {
                break;
            };
            let _ = stream.set_read_timeout(Some(Duration::from_millis(300)));
            let _ = stream.set_write_timeout(Some(Duration::from_millis(300)));
            let mut command = String::new();
            if BufReader::new(&stream)
                .take(4096)
                .read_line(&mut command)
                .is_err()
            {
                continue;
            }
            let command = command.trim_end_matches(['\r', '\n']);
            match command {
                "toggle" | "cancel" => {
                    if send.send(command.to_owned()).is_ok() {
                        let _ = stream.write_all(b"ok\n");
                    }
                }
                value if value.starts_with("replay\t") => {
                    if send.send(value.to_owned()).is_ok() {
                        let _ = stream.write_all(b"ok\n");
                    }
                }
                "status" => {
                    let view = lock(&control_view.view);
                    let status = if !view.ready {
                        "loading"
                    } else {
                        match view.phase {
                            pipeline::Phase::Arming | pipeline::Phase::Listening => "recording",
                            pipeline::Phase::Finishing => "finishing",
                            _ => "idle",
                        }
                    };
                    let _ = stream.write_all(format!("{status}\n").as_bytes());
                }
                _ => {
                    let _ = stream.write_all(b"Unknown command\n");
                }
            }
        }
    });
    pipeline::start_worker(Arc::clone(&shared));
    let outcome = ui::run(shared, Some(receive), false);
    let _ = fs::remove_file(path);
    outcome
}

/// Benchmark the final accuracy pass silently, without microphone or insertion.
fn transcribe_file(path: &Path, repeat: usize) -> Result<()> {
    let audio = hound::WavReader::open(path)?;
    let spec = audio.spec();
    anyhow::ensure!(
        spec.channels == 1
            && spec.sample_rate == 16000
            && spec.bits_per_sample == 16
            && spec.sample_format == hound::SampleFormat::Int,
        "Expected mono 16 kHz PCM16 WAV"
    );
    let seconds = audio.duration() as f64 / 16000.0;
    let started = Instant::now();
    let mut session = recognizer::load()?;
    let load_ms = started.elapsed().as_secs_f64() * 1000.0;
    let mut text = String::new();
    let pcm: Vec<f32> = hound::WavReader::open(path)?
        .samples::<i16>()
        .map(|sample| sample.map(|value| value as f32 / 32768.0))
        .collect::<std::result::Result<_, _>>()?;
    let mut run_times = Vec::new();
    for _ in 0..repeat {
        let started = Instant::now();
        text = recognizer::transcribe(&mut session, &pcm)?;
        run_times.push(started.elapsed().as_secs_f64() * 1000.0);
    }

    println!(
        "{}",
        serde_json::json!({"text":text, "audio_secs":seconds, "load_ms":load_ms,
        "transcribe_ms":run_times, "bound_backend":session.backend,
        "model":"live-parakeet-ultra-Q8_0", "mode":"full_file_accuracy_pass",
        "corrected_text":dictation::normalize(&text, &dictation::load_rules().map_err(|e| anyhow::anyhow!(e.to_string()))?)})
    );
    Ok(())
}

fn run() -> Result<()> {
    let arguments: Vec<String> = env::args().skip(1).collect();
    match arguments.as_slice() {
        [command] if command == "serve" => serve(),
        [command] if ["toggle", "cancel", "status"].contains(&command.as_str()) => request(command),
        [command] if command == "demo" => ui::run(Shared::new(), None, true),
        [command, path] if command == "replay" => {
            let path = fs::canonicalize(path)?;
            let path = path.to_str().context("Replay path must be UTF-8")?;
            anyhow::ensure!(
                !path.contains(['\n', '\r']) && path.len() < 3900,
                "Invalid replay path"
            );
            request(&format!("replay\t{path}"))
        }
        [command, path] if command == "transcribe-file" => transcribe_file(Path::new(path), 1),
        [command, path, option, count] if command == "transcribe-file" && option == "--repeat" => {
            let repeat: usize = count.parse()?;
            anyhow::ensure!(
                (1..=10).contains(&repeat),
                "Repeat must be between 1 and 10"
            );
            transcribe_file(Path::new(path), repeat)
        }
        [] => {
            println!(
                "dictation-live serve | toggle | cancel | status | demo\ndictation-live replay AUDIO.wav        Silent real-time preview; no microphone or paste\ndictation-live transcribe-file AUDIO.wav  Silent recognition benchmark (JSON)\n\nF11 / Super+D toggles dictation. The demo never records or inserts text."
            );
            Ok(())
        }
        _ => bail!(
            "Use: dictation-live serve | toggle | cancel | status | demo | transcribe-file AUDIO.wav"
        ),
    }
}

fn main() {
    if let Err(error) = run() {
        eprintln!("dictation-live: {error:#}");
        std::process::exit(1);
    }
}
