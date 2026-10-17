use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::PathBuf;
use std::process::{Command, Output};
use std::sync::atomic::{AtomicUsize, Ordering};

static NEXT_ID: AtomicUsize = AtomicUsize::new(0);

struct Sandbox(PathBuf);

impl Sandbox {
    fn new(clipboard_script: &str) -> Self {
        let directory = std::env::temp_dir().join(format!(
            "dictation-test-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&directory).unwrap();
        for (name, script) in [
            ("wl-copy", clipboard_script),
            (
                "wl-paste",
                "test -f \"$DICTATION_TEST_DIR/clipboard\" || exit 1\nif [ \"$1\" = --list-types ]; then printf '%s\\n' \"${DICTATION_TEST_MIME:-text/plain;charset=utf-8}\"; else cat \"$DICTATION_TEST_DIR/clipboard\"; fi",
            ),
            (
                "wtype",
                "cp \"$DICTATION_TEST_DIR/clipboard\" \"$DICTATION_TEST_DIR/inserted\"\nprintf '%s\\n' \"$@\" > \"$DICTATION_TEST_DIR/keys\"\nexit \"${DICTATION_TEST_KEY_STATUS:-0}\"",
            ),
        ] {
            let path = directory.join(name);
            fs::write(&path, format!("#!/bin/sh\n{script}\n")).unwrap();
            fs::set_permissions(path, fs::Permissions::from_mode(0o755)).unwrap();
        }
        Self(directory)
    }

    fn paste(&self, text: &str) -> Output {
        self.command(text).output().unwrap()
    }

    fn command(&self, text: &str) -> Command {
        self.cli(&["paste", text])
    }

    fn cli(&self, arguments: &[&str]) -> Command {
        let mut command = Command::new(env!("CARGO_BIN_EXE_dictation"));
        command
            .args(arguments)
            .env(
                "PATH",
                format!(
                    "{}:{}",
                    self.0.display(),
                    std::env::var("PATH").unwrap_or_default()
                ),
            )
            .env("DICTATION_TEST_DIR", &self.0)
            .env("DICTATION_CACHE_DIR", self.0.join("history"))
            .env_remove("DICTATION_HISTORY")
            .env(
                "DICTATION_TERMS",
                concat!(env!("CARGO_MANIFEST_DIR"), "/terms.tsv"),
            );
        command
    }
}

impl Drop for Sandbox {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

#[test]
fn pastes_corrected_unicode_and_literal_shell_characters() {
    let sandbox = Sandbox::new(
        "if [ \"$1\" = --clear ]; then rm -f \"$DICTATION_TEST_DIR/clipboard\"; else cat > \"$DICTATION_TEST_DIR/clipboard\"; fi",
    );
    let output = sandbox.paste("Vi bruger ddpm og i m f; $(false) `false` 'æøå'\nmean flow.");
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert_eq!(
        fs::read_to_string(sandbox.0.join("inserted")).unwrap(),
        "Vi bruger DDPM og iMF; $(false) `false` 'æøå'\nMeanFlow."
    );
    assert!(!sandbox.0.join("clipboard").exists());
    assert_eq!(
        fs::read_to_string(sandbox.0.join("keys")).unwrap(),
        "-M\nctrl\n-M\nshift\n-P\nv\n-p\nv\n-m\nshift\n-m\nctrl\n"
    );
}

#[test]
fn restores_existing_text_and_screenshot_bytes_even_when_typing_fails() {
    for (mime, bytes, key_status) in [
        (
            "text/plain;charset=utf-8",
            "Already copied: imf and æøå\n".as_bytes(),
            "0",
        ),
        (
            "image/png",
            b"\x89PNG\r\n\x1a\n\x00\xff\x80".as_slice(),
            "0",
        ),
        ("image/png", b"\x89PNG\x00\xff".as_slice(), "3"),
    ] {
        let sandbox = Sandbox::new("cat > \"$DICTATION_TEST_DIR/clipboard\"");
        fs::write(sandbox.0.join("clipboard"), bytes).unwrap();
        let result = sandbox
            .command("ddpm")
            .env("DICTATION_TEST_MIME", mime)
            .env("DICTATION_TEST_KEY_STATUS", key_status)
            .output()
            .unwrap();
        assert_eq!(result.status.success(), key_status == "0");
        assert_eq!(fs::read(sandbox.0.join("clipboard")).unwrap(), bytes);
        assert_eq!(
            fs::read_to_string(sandbox.0.join("inserted")).unwrap(),
            "DDPM"
        );
    }
}

#[test]
fn clipboard_failure_never_pastes_stale_text() {
    let sandbox = Sandbox::new("exit 3");
    assert!(!sandbox.paste("ddpm").status.success());
    assert!(!sandbox.0.join("keys").exists());
    assert!(!sandbox.0.join("history/history.jsonl").exists());
}

#[test]
fn silence_never_changes_clipboard_or_sends_keys() {
    let sandbox = Sandbox::new("cat > \"$DICTATION_TEST_DIR/clipboard\"");
    assert!(sandbox.paste("  \n\t").status.success());
    assert!(!sandbox.0.join("clipboard").exists());
    assert!(!sandbox.0.join("keys").exists());
    assert!(!sandbox.0.join("history/history.jsonl").exists());
}

#[test]
fn successful_dictation_is_cached_for_review_and_can_be_cleared() {
    let sandbox = Sandbox::new(
        "if [ \"$1\" = --clear ]; then rm -f \"$DICTATION_TEST_DIR/clipboard\"; else cat > \"$DICTATION_TEST_DIR/clipboard\"; fi",
    );
    assert!(sandbox.paste("imf\nmean flow æøå").status.success());
    let path = sandbox.0.join("history/history.jsonl");
    let records = fs::read_to_string(&path).unwrap();
    assert_eq!(records.lines().count(), 1);
    assert!(records.contains("\"recognized\":\"imf\\nmean flow æøå\""));
    assert!(records.contains("\"inserted\":\"iMF\\nMeanFlow æøå\""));
    let recent = sandbox.cli(&["history", "1"]).output().unwrap();
    assert!(recent.status.success());
    assert_eq!(String::from_utf8(recent.stdout).unwrap(), records);
    let location = sandbox.cli(&["history", "path"]).output().unwrap();
    assert_eq!(
        String::from_utf8(location.stdout).unwrap().trim(),
        path.to_str().unwrap()
    );
    assert!(
        sandbox
            .cli(&["history", "clear"])
            .status()
            .unwrap()
            .success()
    );
    assert_eq!(fs::read_to_string(path).unwrap(), "");
}

#[test]
fn cache_errors_do_not_break_pasting_and_caching_can_be_disabled() {
    let sandbox = Sandbox::new("cat > \"$DICTATION_TEST_DIR/clipboard\"");
    let blocked = sandbox.0.join("not-a-directory");
    fs::write(&blocked, "").unwrap();
    let result = sandbox
        .command("ddpm")
        .env("DICTATION_CACHE_DIR", blocked)
        .output()
        .unwrap();
    assert!(result.status.success());
    assert_eq!(
        fs::read_to_string(sandbox.0.join("inserted")).unwrap(),
        "DDPM"
    );
    assert!(
        String::from_utf8(result.stderr)
            .unwrap()
            .contains("could not cache transcript")
    );
    assert!(
        sandbox
            .command("imf")
            .env("DICTATION_HISTORY", "0")
            .status()
            .unwrap()
            .success()
    );
    assert!(!sandbox.0.join("history/history.jsonl").exists());
    assert!(
        sandbox
            .cli(&["normalize", "ddpm"])
            .output()
            .unwrap()
            .status
            .success()
    );
    assert!(!sandbox.0.join("history/history.jsonl").exists());
}
