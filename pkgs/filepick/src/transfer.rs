use anyhow::{bail, Context, Result};
use std::{
    collections::BTreeSet,
    env, fs,
    io::{self, BufRead, Read, Write},
    os::unix::{
        ffi::{OsStrExt, OsStringExt},
        fs::{DirBuilderExt, PermissionsExt},
        process::CommandExt,
    },
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::mpsc,
    time::Duration,
};
use url::Url;
use wl_clipboard_rs::copy::{MimeSource, MimeType, Options, Source};

pub fn home() -> Result<PathBuf> {
    env::var_os("HOME")
        .map(PathBuf::from)
        .context("HOME is not set; specify a search folder")
}

pub fn validate(paths: &[PathBuf]) -> Result<Vec<PathBuf>> {
    if paths.is_empty() {
        bail!("No files selected");
    }
    let mut files = BTreeSet::new();
    for path in paths {
        // Keep symlink names, but require a regular readable target.
        let absolute = std::path::absolute(path)?;
        let metadata = fs::metadata(&absolute)
            .with_context(|| format!("File unavailable: {}", path.display()))?;
        if !metadata.is_file() {
            bail!("Not a regular file: {}", path.display());
        }
        fs::File::open(&absolute)
            .with_context(|| format!("File is unreadable: {}", path.display()))?;
        files.insert(absolute);
    }
    Ok(files.into_iter().collect())
}

fn encode(paths: &[PathBuf]) -> Vec<u8> {
    let mut bytes = Vec::new();
    for path in paths {
        bytes.extend_from_slice(path.as_os_str().as_bytes());
        bytes.push(0);
    }
    bytes
}

fn decode(bytes: &[u8]) -> Vec<PathBuf> {
    bytes
        .split(|byte| *byte == 0)
        .filter(|part| !part.is_empty())
        .map(|part| PathBuf::from(std::ffi::OsString::from_vec(part.to_vec())))
        .collect()
}

fn selection_path() -> Result<PathBuf> {
    let state = match env::var_os("XDG_STATE_HOME").filter(|s| !s.is_empty()) {
        Some(path) => PathBuf::from(path),
        None => home()?.join(".local/state"),
    };
    Ok(state.join("filepick/selection"))
}

pub fn save_selection(paths: &[PathBuf]) -> Result<()> {
    let path = selection_path()?;
    let parent = path.parent().unwrap();
    fs::DirBuilder::new()
        .recursive(true)
        .mode(0o700)
        .create(parent)?;
    fs::set_permissions(parent, fs::Permissions::from_mode(0o700))?;
    let mut temp = tempfile::NamedTempFile::new_in(parent)?;
    temp.write_all(&encode(paths))?;
    temp.persist(path)
        .context("Could not save selection for --drag-last")?;
    Ok(())
}

pub fn load_selection() -> Result<Vec<PathBuf>> {
    let bytes = fs::read(selection_path()?)
        .context("No saved selection; copy files with filepick first")?;
    validate(&decode(&bytes))
}

fn payloads(files: &[PathBuf], paths_only: bool) -> Result<Vec<MimeSource>> {
    let source = |mime: &str, data: Vec<u8>| MimeSource {
        source: Source::Bytes(data.into_boxed_slice()),
        mime_type: MimeType::Specific(mime.to_owned()),
    };
    let mut paths = Vec::new();
    for (i, path) in files.iter().enumerate() {
        if i > 0 {
            paths.push(b'\n');
        }
        paths.extend_from_slice(path.as_os_str().as_bytes());
    }
    if paths_only {
        return Ok(vec![
            source("text/plain;charset=utf-8", paths.clone()),
            source("text/plain", paths),
        ]);
    }
    let uris: Result<Vec<_>> = files
        .iter()
        .map(|p| {
            Url::from_file_path(p)
                .map(|uri| uri.to_string())
                .map_err(|_| anyhow::anyhow!("Cannot encode path: {}", p.display()))
        })
        .collect();
    let uris = uris?;
    Ok(vec![
        source(
            "text/uri-list",
            format!("{}\r\n", uris.join("\r\n")).into_bytes(),
        ),
        source(
            "x-special/gnome-copied-files",
            format!("copy\n{}", uris.join("\n")).into_bytes(),
        ),
        source("application/x-kde-cutselection", b"0".to_vec()),
        // Terminals and local coding assistants request text, not file URI
        // lists. Offer the complete selection without replacing the native
        // formats used by file managers and browser upload controls.
        source("text/plain;charset=utf-8", paths.clone()),
        source("text/plain", paths),
    ])
}

pub fn serve(paths_only: bool) -> Result<()> {
    let mut input = Vec::new();
    io::stdin().read_to_end(&mut input)?;
    let files = validate(&decode(&input))?;
    let mut options = Options::new();
    options
        .foreground(true)
        .omit_additional_text_mime_types(!paths_only);
    let clipboard = options.prepare_copy_multi(payloads(&files, paths_only)?)?;
    println!("READY");
    io::stdout().flush()?;
    clipboard.serve()?;
    Ok(())
}

pub fn copy(files: &[PathBuf], paths_only: bool) -> Result<()> {
    let mut command = Command::new(env::current_exe()?);
    command.process_group(0);
    command.arg("--serve-clipboard");
    if paths_only {
        command.arg("--paths");
    }
    // A separate process owns the clipboard after the picker/terminal closes.
    let mut child = command
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()?;
    let result = (|| -> Result<()> {
        child.stdin.take().unwrap().write_all(&encode(files))?;
        let mut output = io::BufReader::new(child.stdout.take().unwrap());
        let (tx, rx) = mpsc::channel();
        std::thread::spawn(move || {
            let mut line = String::new();
            let _ = output.read_line(&mut line);
            let _ = tx.send(line);
        });
        if rx.recv_timeout(Duration::from_secs(8))?.trim() != "READY" {
            let mut error = String::new();
            child.stderr.take().unwrap().read_to_string(&mut error)?;
            bail!(
                "{}. Use d / --drag-last, or --print over SSH.",
                error.trim()
            );
        }
        Ok(())
    })();
    if result.is_err() {
        let _ = child.kill();
        let _ = child.wait();
    }
    result.context("Could not copy to the Wayland clipboard")
}

fn drag_command(files: &[PathBuf]) -> Command {
    let mut command = Command::new("dragon-drop");
    command.args(["--all", "--and-exit", "--on-top"]);
    // Paths are absolute, so even filenames beginning with '-' are arguments.
    command.args(files);
    command
}

pub fn drag(files: &[PathBuf]) -> Result<()> {
    let files = validate(files)?;
    eprintln!(
        "Hold the left mouse button on the file group, drag to the upload box, then release."
    );
    let error = drag_command(&files).exec();
    Err(error).context("Cannot start dragon-drop (install the desktop package); files remain available with --drag-last")
}

pub fn notify_copied(count: usize, paths_only: bool) {
    let message = if paths_only {
        format!("Copied {count} file paths.")
    } else {
        format!(
            "Copied all {count} files. Paste in the destination, or Super+Alt+D to drag the group."
        )
    };
    notify(&message);
}

pub fn notify(message: &str) {
    let _ = Command::new("notify-send")
        .args(["Filepick", message])
        .status();
}

pub fn clean(text: &str) -> String {
    text.chars()
        .map(|c| if c.is_control() { ' ' } else { c })
        .collect()
}

pub fn preview(path: &Path) -> String {
    let Ok(metadata) = fs::metadata(path) else {
        return "File unavailable".into();
    };
    if !metadata.is_file() {
        return "Not a regular file".into();
    }
    let mut bytes = Vec::new();
    let result = fs::File::open(path).and_then(|f| f.take(8192).read_to_end(&mut bytes));
    let mut text = format!(
        "{}\n{} bytes\n\n",
        clean(&path.display().to_string()),
        metadata.len()
    );
    if result.is_err() {
        text.push_str("Cannot read file");
    } else if bytes.contains(&0) {
        text.push_str("Binary file — use d to drag into an upload area.");
    } else {
        for line in String::from_utf8_lossy(&bytes).lines().take(100) {
            text.push_str(&clean(line));
            text.push('\n');
        }
        if metadata.len() > bytes.len() as u64 {
            text.push_str("\n… preview truncated");
        }
    }
    text
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn manifest_preserves_unusual_unix_filenames() {
        let paths = vec![
            PathBuf::from("/tmp/a\nb c"),
            PathBuf::from(std::ffi::OsString::from_vec(b"/tmp/raw\xff".to_vec())),
        ];
        assert_eq!(decode(&encode(&paths)), paths);
    }

    #[test]
    fn file_clipboard_escapes_paths_and_advertises_copy() {
        let sources = payloads(
            &[PathBuf::from("/tmp/a #%.pdf"), PathBuf::from("/tmp/a\nb")],
            false,
        )
        .unwrap();
        let Source::Bytes(bytes) = &sources[0].source else {
            panic!()
        };
        assert_eq!(
            &**bytes,
            b"file:///tmp/a%20%23%25.pdf\r\nfile:///tmp/a%0Ab\r\n"
        );
        let Source::Bytes(bytes) = &sources[1].source else {
            panic!()
        };
        assert!(bytes.starts_with(b"copy\nfile:///"));
        assert_eq!(sources.len(), 5);
        let Source::Bytes(bytes) = &sources[3].source else {
            panic!()
        };
        assert_eq!(&**bytes, b"/tmp/a #%.pdf\n/tmp/a\nb");
        let Source::Bytes(bytes) = &sources[4].source else {
            panic!()
        };
        assert_eq!(&**bytes, b"/tmp/a #%.pdf\n/tmp/a\nb");
    }

    #[test]
    fn selection_rejects_missing_files_and_directories_and_deduplicates() {
        let dir = tempfile::tempdir().unwrap();
        let file = dir.path().join("file");
        fs::write(&file, "hello").unwrap();
        assert_eq!(validate(&[file.clone(), file.clone()]).unwrap(), vec![file]);
        assert!(validate(&[dir.path().to_owned()]).is_err());
        assert!(validate(&[dir.path().join("missing")]).is_err());
        assert!(validate(&[]).is_err());
    }

    #[test]
    fn drag_passes_unusual_names_as_individual_arguments() {
        let files = vec![
            PathBuf::from("/tmp/-file;$(hello)\n.pdf"),
            PathBuf::from("/tmp/a b"),
        ];
        let command = drag_command(&files);
        let args: Vec<_> = command.get_args().collect();
        assert_eq!(&args[3..], &[files[0].as_os_str(), files[1].as_os_str()]);
    }

    #[test]
    fn preview_does_not_emit_terminal_escape_sequences() {
        let file = tempfile::NamedTempFile::new().unwrap();
        fs::write(file.path(), "hello\x1b]52;c;payload\x07\nworld").unwrap();
        let output = preview(file.path());
        assert!(!output.contains('\x1b'));
        assert!(!output.contains('\x07'));
        assert!(output.contains("world"));
    }
}
