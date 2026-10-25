use crate::Result;
use std::env;
use std::fs::{self, DirBuilder, OpenOptions};
use std::io::Write;
use std::os::unix::fs::{DirBuilderExt, OpenOptionsExt, PermissionsExt};
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

const MAX_ENTRIES: usize = 500;
const MAX_BYTES: usize = 2 * 1024 * 1024;
const MAX_TEXT_BYTES: usize = 16 * 1024;

pub struct History {
    directory: PathBuf,
}

impl History {
    pub fn configured() -> Result<Self> {
        let directory = if let Some(path) = env::var_os("DICTATION_CACHE_DIR") {
            PathBuf::from(path)
        } else {
            let cache = env::var_os("XDG_CACHE_HOME")
                .map(PathBuf::from)
                .or_else(|| env::var_os("HOME").map(|home| PathBuf::from(home).join(".cache")))
                .ok_or("Set XDG_CACHE_HOME or HOME for the dictation cache")?;
            cache.join("dictation")
        };
        Ok(Self { directory })
    }

    pub fn path(&self) -> PathBuf {
        self.directory.join("history.jsonl")
    }

    fn lock(&self) -> Result<std::fs::File> {
        DirBuilder::new()
            .recursive(true)
            .mode(0o700)
            .create(&self.directory)?;
        fs::set_permissions(&self.directory, fs::Permissions::from_mode(0o700))?;
        let file = OpenOptions::new()
            .create(true)
            .truncate(false)
            .write(true)
            .mode(0o600)
            .open(self.directory.join("history.lock"))?;
        file.lock()?;
        Ok(file)
    }

    fn read(&self) -> Result<Vec<String>> {
        match fs::read_to_string(self.path()) {
            Ok(contents) => Ok(contents
                .lines()
                .filter(|line| !line.is_empty())
                .map(str::to_string)
                .collect()),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(Vec::new()),
            Err(error) => Err(error.into()),
        }
    }

    fn replace(&self, records: &[String]) -> Result<()> {
        let temporary = self.directory.join(format!(
            ".history-{}-{}.tmp",
            std::process::id(),
            SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos()
        ));
        let result = (|| -> Result<()> {
            let mut file = OpenOptions::new()
                .write(true)
                .create_new(true)
                .mode(0o600)
                .open(&temporary)?;
            for record in records {
                writeln!(file, "{record}")?;
            }
            file.flush()?;
            fs::rename(&temporary, self.path())?;
            Ok(())
        })();
        if result.is_err() {
            let _ = fs::remove_file(temporary);
        }
        result
    }

    pub fn record(&self, recognized: &str, inserted: &str) -> Result<()> {
        let _lock = self.lock()?;
        let timestamp = SystemTime::now().duration_since(UNIX_EPOCH)?.as_millis();
        let truncated = recognized.len() > MAX_TEXT_BYTES || inserted.len() > MAX_TEXT_BYTES;
        let record = format!(
            "{{\"version\":1,\"timestamp_unix_ms\":{timestamp},\"recognized\":{},\"inserted\":{},\"truncated\":{truncated}}}",
            json_string(shorten(recognized)),
            json_string(shorten(inserted))
        );
        let mut records = self.read()?;
        records.push(record);
        retain_recent(&mut records);
        self.replace(&records)
    }

    pub fn recent(&self, count: usize) -> Result<Vec<String>> {
        let _lock = self.lock()?;
        let records = self.read()?;
        Ok(records
            .into_iter()
            .rev()
            .take(count.min(MAX_ENTRIES))
            .collect::<Vec<_>>()
            .into_iter()
            .rev()
            .collect())
    }

    pub fn clear(&self) -> Result<()> {
        let _lock = self.lock()?;
        self.replace(&[])
    }
}

pub fn record(recognized: &str, inserted: &str) {
    if env::var_os("DICTATION_HISTORY").is_some_and(|value| value == "0") {
        return;
    }
    if let Err(error) =
        History::configured().and_then(|history| history.record(recognized, inserted))
    {
        // History is best-effort: a full disk must not make successful typing fail.
        eprintln!("dictation: could not cache transcript: {error}");
    }
}

fn shorten(text: &str) -> &str {
    let mut end = text.len().min(MAX_TEXT_BYTES);
    while !text.is_char_boundary(end) {
        end -= 1;
    }
    &text[..end]
}

fn json_string(text: &str) -> String {
    let mut result = String::with_capacity(text.len() + 2);
    result.push('"');
    for character in text.chars() {
        match character {
            '"' => result.push_str("\\\""),
            '\\' => result.push_str("\\\\"),
            '\n' => result.push_str("\\n"),
            '\r' => result.push_str("\\r"),
            '\t' => result.push_str("\\t"),
            '\u{0000}'..='\u{001f}' => {
                use std::fmt::Write;
                let _ = write!(result, "\\u{:04x}", character as u32);
            }
            character => result.push(character),
        }
    }
    result.push('"');
    result
}

fn retain_recent(records: &mut Vec<String>) {
    let mut bytes = 0;
    let keep = records
        .iter()
        .rev()
        .take(MAX_ENTRIES)
        .take_while(|record| {
            bytes += record.len() + 1;
            bytes <= MAX_BYTES
        })
        .count();
    records.drain(..records.len() - keep);
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};

    static NEXT_ID: AtomicUsize = AtomicUsize::new(0);

    struct Sandbox(History);
    impl Sandbox {
        fn new() -> Self {
            Self(History {
                directory: env::temp_dir().join(format!(
                    "dictation-history-test-{}-{}",
                    std::process::id(),
                    NEXT_ID.fetch_add(1, Ordering::Relaxed)
                )),
            })
        }
    }
    impl Drop for Sandbox {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0.directory);
        }
    }

    #[test]
    fn caches_unicode_escaped_records_privately_and_clears_them() {
        let sandbox = Sandbox::new();
        let history = &sandbox.0;
        history.record("imf\n\"æøå\"\t\\\u{0000}", "iMF").unwrap();
        let rows = history.recent(20).unwrap();
        assert_eq!(rows.len(), 1);
        assert!(rows[0].contains("\"recognized\":\"imf\\n\\\"æøå\\\"\\t\\\\\\u0000\""));
        assert!(rows[0].contains("\"inserted\":\"iMF\""));
        assert!(rows[0].contains("\"truncated\":false"));
        assert_eq!(
            fs::metadata(&history.directory)
                .unwrap()
                .permissions()
                .mode()
                & 0o777,
            0o700
        );
        assert_eq!(
            fs::metadata(history.path()).unwrap().permissions().mode() & 0o777,
            0o600
        );
        history.clear().unwrap();
        assert!(history.recent(20).unwrap().is_empty());
    }

    #[test]
    fn retention_limits_keep_whole_newest_entries() {
        let mut records: Vec<_> = (0..510).map(|n| n.to_string()).collect();
        retain_recent(&mut records);
        assert_eq!(records.len(), 500);
        assert_eq!(records.first().unwrap(), "10");
        assert_eq!(records.last().unwrap(), "509");
        let large = "x".repeat(MAX_BYTES / 3);
        records = vec![
            large.clone(),
            large.clone(),
            large.clone(),
            "newest".to_string(),
        ];
        retain_recent(&mut records);
        assert_eq!(records, vec![large.clone(), large, "newest".to_string()]);
    }

    #[test]
    fn long_transcripts_are_marked_and_truncated_on_utf8_boundaries() {
        let sandbox = Sandbox::new();
        sandbox
            .0
            .record(&"æøå🙂".repeat(MAX_TEXT_BYTES), "iMF")
            .unwrap();
        let rows = sandbox.0.recent(1).unwrap();
        assert!(rows[0].contains("\"truncated\":true"));
        assert!(rows[0].len() < MAX_TEXT_BYTES + 200);
        assert!(shorten(&"🙂".repeat(MAX_TEXT_BYTES)).len() <= MAX_TEXT_BYTES);
    }

    #[test]
    fn concurrent_records_are_not_lost() {
        let sandbox = Sandbox::new();
        std::thread::scope(|scope| {
            for _ in 0..4 {
                let history = &sandbox.0;
                scope.spawn(move || {
                    for _ in 0..10 {
                        history.record("imf", "iMF").unwrap();
                    }
                });
            }
        });
        assert_eq!(sandbox.0.recent(500).unwrap().len(), 40);
    }
}
