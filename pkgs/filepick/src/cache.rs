use std::{
    collections::hash_map::DefaultHasher,
    fs,
    hash::{Hash, Hasher},
    io::{self, Write},
    os::unix::{
        ffi::{OsStrExt, OsStringExt},
        fs::{DirBuilderExt, MetadataExt, PermissionsExt},
    },
    path::{Path, PathBuf},
};

const MAGIC: &[u8] = b"FILEPICK-INDEX\0\x03";

#[derive(Clone, Debug, PartialEq, Eq)]
struct Fingerprint([u64; 8]);

impl Fingerprint {
    fn read(path: &Path) -> Option<Self> {
        fs::metadata(path).ok().map(|m| {
            Self([
                m.dev(),
                m.ino(),
                m.len(),
                m.mtime() as u64,
                m.mtime_nsec() as u64,
                m.ctime() as u64,
                m.ctime_nsec() as u64,
                m.nlink(),
            ])
        })
    }
}

#[derive(Clone, Debug)]
pub struct Stamp {
    path: PathBuf,
    fingerprint: Option<Fingerprint>,
}

impl Stamp {
    pub fn new(path: PathBuf) -> Self {
        let fingerprint = Fingerprint::read(&path);
        Self { path, fingerprint }
    }

    pub fn matches(&self) -> bool {
        Fingerprint::read(&self.path) == self.fingerprint
    }
}

#[derive(Debug, Default)]
pub struct Index {
    pub files: Vec<PathBuf>,
    pub stamps: Vec<Stamp>,
    pub errors: usize,
}

impl Index {
    pub fn unchanged(&self) -> bool {
        self.stamps.iter().all(Stamp::matches)
    }
}

pub fn key<T: Hash>(value: &T) -> u64 {
    let mut hasher = DefaultHasher::new();
    value.hash(&mut hasher);
    hasher.finish()
}

pub fn directory() -> Option<PathBuf> {
    let base = std::env::var_os("XDG_CACHE_HOME")
        .filter(|s| !s.is_empty())
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|h| PathBuf::from(h).join(".cache")))?;
    Some(base.join("filepick"))
}

pub fn path(key: u64) -> Option<PathBuf> {
    Some(directory()?.join(format!("{key:016x}.index")))
}

fn write_path(out: &mut impl Write, path: &Path) -> io::Result<()> {
    let bytes = path.as_os_str().as_bytes();
    let len = u32::try_from(bytes.len()).map_err(|_| io::ErrorKind::InvalidData)?;
    out.write_all(&len.to_le_bytes())?;
    out.write_all(bytes)
}

fn write(index: &Index, key: u64, out: &mut impl Write) -> io::Result<()> {
    out.write_all(MAGIC)?;
    for value in [
        key,
        index.errors as u64,
        index.files.len() as u64,
        index.stamps.len() as u64,
    ] {
        out.write_all(&value.to_le_bytes())?;
    }
    for path in &index.files {
        write_path(out, path)?;
    }
    for stamp in &index.stamps {
        write_path(out, &stamp.path)?;
        out.write_all(&[u8::from(stamp.fingerprint.is_some())])?;
        if let Some(Fingerprint(values)) = &stamp.fingerprint {
            for value in values {
                out.write_all(&value.to_le_bytes())?;
            }
        }
    }
    Ok(())
}

pub fn save(index: &Index, key: u64, path: &Path) -> io::Result<()> {
    let parent = path.parent().ok_or(io::ErrorKind::InvalidInput)?;
    fs::DirBuilder::new()
        .recursive(true)
        .mode(0o700)
        .create(parent)?;
    fs::set_permissions(parent, fs::Permissions::from_mode(0o700))?;
    let mut temporary = tempfile::NamedTempFile::new_in(parent)?;
    let mut writer = io::BufWriter::new(temporary.as_file_mut());
    write(index, key, &mut writer)?;
    writer.flush()?;
    drop(writer);
    temporary.persist(path).map_err(|e| e.error)?;
    Ok(())
}

struct Reader<'a>(&'a [u8]);
impl<'a> Reader<'a> {
    fn take(&mut self, len: usize) -> Option<&'a [u8]> {
        let bytes = self.0.get(..len)?;
        self.0 = &self.0[len..];
        Some(bytes)
    }
    fn u64(&mut self) -> Option<u64> {
        Some(u64::from_le_bytes(self.take(8)?.try_into().ok()?))
    }
    fn count(&mut self) -> Option<usize> {
        usize::try_from(self.u64()?).ok()
    }
    fn path(&mut self) -> Option<PathBuf> {
        let len = u32::from_le_bytes(self.take(4)?.try_into().ok()?) as usize;
        let bytes = self.take(len)?;
        if bytes.is_empty() || bytes.contains(&0) {
            return None;
        }
        let path = PathBuf::from(std::ffi::OsString::from_vec(bytes.to_vec()));
        path.is_absolute().then_some(path)
    }
}

fn read(bytes: &[u8], key: u64) -> Option<Index> {
    let mut reader = Reader(bytes);
    if reader.take(MAGIC.len())? != MAGIC || reader.u64()? != key {
        return None;
    }
    let errors = reader.count()?;
    let count = reader.count()?;
    let stamps = reader.count()?;
    // Every record needs at least a length and one path byte. Reject corrupt counts
    // before allocating; incomplete caches fall back to a normal scan.
    if count > reader.0.len() / 5 || stamps > reader.0.len() / 6 {
        return None;
    }
    let mut index = Index {
        files: Vec::with_capacity(count),
        stamps: Vec::with_capacity(stamps),
        errors,
    };
    for _ in 0..count {
        index.files.push(reader.path()?);
    }
    for _ in 0..stamps {
        let path = reader.path()?;
        let fingerprint = match reader.take(1)?[0] {
            0 => None,
            1 => {
                let mut values = [0; 8];
                for value in &mut values {
                    *value = reader.u64()?;
                }
                Some(Fingerprint(values))
            }
            _ => return None,
        };
        index.stamps.push(Stamp { path, fingerprint });
    }
    reader.0.is_empty().then_some(index)
}

pub fn load(key: u64, path: &Path) -> Option<Index> {
    let file = fs::File::open(path).ok()?;
    if file.metadata().ok()?.len() > 512 * 1024 * 1024 {
        return None;
    }
    let mut bytes = Vec::new();
    use io::Read;
    file.take(512 * 1024 * 1024 + 1)
        .read_to_end(&mut bytes)
        .ok()?;
    read(&bytes, key)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn index_roundtrips_raw_unix_paths_and_detects_directory_changes() {
        let dir = tempfile::tempdir().unwrap();
        let file = dir
            .path()
            .join(std::ffi::OsString::from_vec(b"a\n\xff".to_vec()));
        fs::write(&file, "hello").unwrap();
        let index = Index {
            files: vec![file.clone()],
            stamps: vec![Stamp::new(dir.path().to_owned())],
            errors: 3,
        };
        let path = dir.path().join("cache/index");
        save(&index, 42, &path).unwrap();
        let loaded = load(42, &path).unwrap();
        assert_eq!(loaded.files, vec![file]);
        assert_eq!(loaded.errors, 3);
        assert!(load(43, &path).is_none());
        assert_eq!(
            fs::metadata(&path).unwrap().permissions().mode() & 0o777,
            0o600
        );
        assert_eq!(
            fs::metadata(path.parent().unwrap())
                .unwrap()
                .permissions()
                .mode()
                & 0o777,
            0o700
        );
        // Saving the cache created a directory, so the original stamp is stale.
        assert!(!loaded.unchanged());
    }
    #[test]
    fn incomplete_and_corrupt_indexes_are_rejected() {
        let mut bytes = Vec::new();
        write(&Index::default(), 7, &mut bytes).unwrap();
        assert!(read(&bytes, 7).is_some());
        for length in 0..bytes.len() {
            assert!(read(&bytes[..length], 7).is_none());
        }
        bytes[MAGIC.len() + 16..MAGIC.len() + 24].fill(255);
        assert!(read(&bytes, 7).is_none());
    }
    #[test]
    fn stamps_detect_ignore_edits_and_missing_roots() {
        let dir = tempfile::tempdir().unwrap();
        let ignore = dir.path().join(".gitignore");
        let missing = Stamp::new(ignore.clone());
        assert!(missing.matches());
        fs::write(&ignore, "a\n").unwrap();
        assert!(!missing.matches());
        let old = Stamp::new(ignore.clone());
        fs::write(&ignore, "longer\n").unwrap();
        assert!(!old.matches());
    }
}
