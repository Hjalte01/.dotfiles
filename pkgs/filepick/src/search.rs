use crate::cache::{self, Index, Stamp};
use ignore::{DirEntry, WalkBuilder};
use nucleo::{Config, Injector, Nucleo};
use std::{
    collections::BTreeSet,
    fs,
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicBool, AtomicUsize, Ordering},
        mpsc::{self, Receiver},
        Arc,
    },
    thread,
};

const DEFAULT_ROOTS: &str = "Downloads\nDesktop\nDocuments\nPictures\nVideos\nMusic\nPublic\nTemplates\nProjects\nprojects\nsrc\n.dotfiles\nZotero/storage\n";
const IGNORE_NAMES: [&str; 3] = [".gitignore", ".ignore", ".filepick-ignore"];

#[derive(Debug)]
pub struct Entry {
    pub path: PathBuf,
    pub label: String,
}

#[derive(Clone)]
struct Policy {
    root: PathBuf,
    all: bool,
    personal: bool,
    roots: Vec<PathBuf>,
    ignore: PathBuf,
    key: u64,
}

fn config_dir() -> PathBuf {
    std::env::var_os("XDG_CONFIG_HOME")
        .filter(|s| !s.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            std::env::var_os("HOME")
                .map(PathBuf::from)
                .unwrap_or_default()
                .join(".config")
        })
        .join("filepick")
}

impl Policy {
    fn new(root: PathBuf, all: bool, personal: bool) -> Self {
        let config = config_dir();
        let roots_text =
            fs::read_to_string(config.join("roots")).unwrap_or_else(|_| DEFAULT_ROOTS.to_owned());
        let ignore = config.join("ignore");
        let ignore_text = fs::read(&ignore).unwrap_or_default();
        let mut roots = Vec::new();
        for line in roots_text
            .lines()
            .map(str::trim)
            .filter(|line| !line.is_empty() && !line.starts_with('#'))
        {
            let path = if let Some(rest) = line.strip_prefix("~/") {
                root.join(rest)
            } else {
                root.join(line)
            };
            if path == root || roots.iter().any(|parent| path.starts_with(parent)) {
                continue;
            }
            roots.retain(|child: &PathBuf| !child.starts_with(&path));
            roots.push(path);
        }
        let key = cache::key(&(3_u32, &root, all, personal, &roots_text, &ignore_text));
        Self {
            root,
            all,
            personal,
            roots,
            ignore,
            key,
        }
    }

    fn useful_file(&self, path: &Path) -> bool {
        if self.all {
            return true;
        }
        if path
            .file_name()
            .is_some_and(|name| name.to_string_lossy().starts_with('.'))
        {
            return false;
        }
        let name = path
            .file_name()
            .unwrap_or_default()
            .to_string_lossy()
            .to_ascii_lowercase();
        if [
            ".pyc",
            ".pyo",
            ".o",
            ".a",
            ".so",
            ".rlib",
            ".rmeta",
            ".class",
            ".lock",
            ".sqlite",
            ".sqlite3",
            ".db",
            ".log",
            ".tmp",
            ".part",
            ".crdownload",
            ".safetensors",
            ".ckpt",
            ".pt",
            ".pth",
            ".onnx",
            ".npy",
            ".npz",
            ".h5",
            ".hdf5",
            ".nii",
            ".nii.gz",
            ".dcm",
            ".iso",
            ".vdi",
            ".vmdk",
            ".qcow2",
            ".pak",
        ]
        .iter()
        .any(|ext| name.ends_with(ext))
        {
            return false;
        }
        if self.personal && path.starts_with(self.root.join("Zotero/storage")) {
            return name.ends_with(".pdf") || name.ends_with(".epub");
        }
        true
    }

    fn include(&self, entry: &DirEntry) -> bool {
        if entry.depth() == 0 {
            return true;
        }
        let path = entry.path();
        // The index must never index its own cache, even in --all mode.
        if entry.file_name() == "filepick" && cache::directory().as_deref() == Some(path) {
            return false;
        }
        if ["/proc", "/sys", "/dev", "/nix", "/run"]
            .iter()
            .any(|skip| path == Path::new(skip))
        {
            return false;
        }
        if self.all || !entry.file_type().is_some_and(|t| t.is_dir()) {
            return true;
        }
        let name = entry.file_name().to_string_lossy();
        if name.starts_with('.') && ![".config", ".github"].contains(&name.as_ref()) {
            return false;
        }
        ![
            "node_modules",
            "target",
            "__pycache__",
            "venv",
            "env",
            "build",
            "dist",
            "result",
            "vendor",
            "site-packages",
            "Cache",
            "Caches",
            "cache",
            "caches",
            "Trash",
            "Steam",
            "steamapps",
            "datasets",
            "checkpoints",
            "wandb",
            "lightning_logs",
            "tensorboard",
        ]
        .contains(&name.as_ref())
    }

    fn walk(&self, root: &Path, shallow: bool) -> ignore::Walk {
        let policy = self.clone();
        let mut walker = WalkBuilder::new(root);
        walker
            .hidden(false)
            .ignore(!self.all)
            .git_ignore(!self.all)
            .git_global(false)
            .git_exclude(false)
            .require_git(false)
            .follow_links(false)
            .add_custom_ignore_filename(".filepick-ignore")
            .filter_entry(move |entry| policy.include(entry));
        if shallow {
            walker.max_depth(Some(1));
        }
        if !self.all && self.ignore.is_file() {
            let _ = walker.add_ignore(&self.ignore);
        }
        walker.build()
    }
}

fn stamp_directory(index: &mut Index, path: &Path) {
    index.stamps.push(Stamp::new(path.to_owned()));
    for name in IGNORE_NAMES {
        let path = path.join(name);
        if path.is_file() {
            index.stamps.push(Stamp::new(path));
        }
    }
}

fn scan(policy: &Policy, cancel: &AtomicBool, mut push: impl FnMut(&Path)) -> Option<Index> {
    let mut index = Index::default();
    // Parent ignore files can affect an explicitly searched subfolder.
    for parent in policy.root.ancestors().skip(1) {
        for name in IGNORE_NAMES {
            index.stamps.push(Stamp::new(parent.join(name)));
        }
    }
    let roots: Vec<_> = if policy.personal && !policy.all {
        std::iter::once((policy.root.clone(), true))
            .chain(policy.roots.iter().map(|p| (p.clone(), false)))
            .collect()
    } else {
        vec![(policy.root.clone(), false)]
    };
    let mut seen = BTreeSet::new();
    for (root, shallow) in roots {
        index.stamps.push(Stamp::new(root.clone()));
        // Missing configured roots must invalidate the cache when created later.
        if !root.is_dir() {
            index.stamps.push(Stamp::new(root));
            continue;
        }
        for result in policy.walk(&root, shallow) {
            if cancel.load(Ordering::Relaxed) {
                return None;
            }
            match result {
                Ok(entry) => {
                    if entry.file_type().is_some_and(|t| t.is_dir()) {
                        if entry.depth() == 0 || !shallow {
                            stamp_directory(&mut index, entry.path());
                        }
                    } else if entry
                        .file_type()
                        .is_some_and(|t| t.is_file() || t.is_symlink() && entry.path().is_file())
                        && policy.useful_file(entry.path())
                        && seen.insert(entry.path().to_owned())
                    {
                        push(entry.path());
                        index.files.push(entry.into_path());
                    }
                }
                Err(_) => {
                    index.errors += 1;
                }
            }
        }
    }
    Some(index)
}

fn inject(injector: &Injector<Entry>, root: &Path, path: PathBuf) {
    let label = path
        .strip_prefix(root)
        .unwrap_or(&path)
        .to_string_lossy()
        .into_owned();
    injector.push(Entry { path, label }, |e, c| c[0] = e.label.as_str().into());
}

pub struct Search {
    pub matcher: Nucleo<Entry>,
    pub done: Arc<AtomicBool>,
    pub errors: Arc<AtomicUsize>,
    pub cached: Arc<AtomicBool>,
    pub rebuilding: Arc<AtomicBool>,
    cancel: Arc<AtomicBool>,
    pending: Receiver<Index>,
    root: PathBuf,
}

impl Search {
    pub fn new(root: PathBuf, all: bool, personal: bool, refresh: bool) -> Self {
        Self::open(
            Policy::new(root, all, personal),
            refresh,
            if cfg!(test) { None } else { cache::directory() },
        )
    }

    fn open(policy: Policy, refresh: bool, cache_dir: Option<PathBuf>) -> Self {
        let matcher = Nucleo::new(Config::DEFAULT.match_paths(), Arc::new(|| {}), Some(2), 1);
        let cancel = Arc::new(AtomicBool::new(false));
        let done = Arc::new(AtomicBool::new(false));
        let errors = Arc::new(AtomicUsize::new(0));
        let cached = Arc::new(AtomicBool::new(false));
        let rebuilding = Arc::new(AtomicBool::new(false));
        let (tx, pending) = mpsc::channel();
        let (c, d, e, h, b) = (
            cancel.clone(),
            done.clone(),
            errors.clone(),
            cached.clone(),
            rebuilding.clone(),
        );
        let injector = matcher.injector();
        let root = policy.root.clone();
        thread::spawn(move || {
            let cache_path = cache_dir.map(|dir| dir.join(format!("{:016x}.index", policy.key)));
            let existing = cache_path
                .as_ref()
                .and_then(|path| cache::load(policy.key, path));
            if let Some(mut index) = existing {
                e.store(index.errors, Ordering::Relaxed);
                for path in std::mem::take(&mut index.files) {
                    if c.load(Ordering::Relaxed) {
                        return;
                    }
                    inject(&injector, &policy.root, path);
                }
                h.store(true, Ordering::Release);
                if !refresh && index.unchanged() {
                    d.store(true, Ordering::Release);
                    return;
                }
                b.store(true, Ordering::Release);
                drop(injector);
                if let Some(index) = scan(&policy, &c, |_| {}) {
                    if let Some(path) = &cache_path {
                        let _ = cache::save(&index, policy.key, path);
                    }
                    let _ = tx.send(index);
                }
            } else if let Some(index) = scan(&policy, &c, |path| {
                inject(&injector, &policy.root, path.to_owned())
            }) {
                e.store(index.errors, Ordering::Relaxed);
                if let Some(path) = &cache_path {
                    let _ = cache::save(&index, policy.key, path);
                }
                d.store(true, Ordering::Release);
            }
        });
        Self {
            matcher,
            done,
            errors,
            cached,
            rebuilding,
            cancel,
            pending,
            root,
        }
    }

    pub fn tick(&mut self, timeout: u64) -> nucleo::Status {
        if let Ok(index) = self.pending.try_recv() {
            self.errors.store(index.errors, Ordering::Relaxed);
            self.matcher.restart(false);
            let injector = self.matcher.injector();
            let root = self.root.clone();
            let (cancel, done, rebuilding) = (
                self.cancel.clone(),
                self.done.clone(),
                self.rebuilding.clone(),
            );
            thread::spawn(move || {
                for path in index.files {
                    if cancel.load(Ordering::Relaxed) {
                        return;
                    }
                    inject(&injector, &root, path);
                }
                rebuilding.store(false, Ordering::Release);
                done.store(true, Ordering::Release);
            });
        }
        self.matcher.tick(timeout)
    }
}

impl Drop for Search {
    fn drop(&mut self) {
        self.cancel.store(true, Ordering::Relaxed);
    }
}

pub struct IndexStats {
    pub files: usize,
    pub directories: usize,
    pub cached: bool,
}

pub fn index(
    root: PathBuf,
    all: bool,
    personal: bool,
    refresh: bool,
) -> anyhow::Result<IndexStats> {
    let policy = Policy::new(root, all, personal);
    let path =
        cache::path(policy.key).ok_or_else(|| anyhow::anyhow!("No cache directory available"))?;
    if !refresh {
        if let Some(index) = cache::load(policy.key, &path) {
            if index.unchanged() {
                return Ok(IndexStats {
                    files: index.files.len(),
                    directories: index.stamps.len(),
                    cached: true,
                });
            }
        }
    }
    let index =
        scan(&policy, &AtomicBool::new(false), |_| {}).expect("Index scan was not cancelled");
    cache::save(&index, policy.key, &path)?;
    Ok(IndexStats {
        files: index.files.len(),
        directories: index.stamps.len(),
        cached: false,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{Duration, Instant};

    fn finish(search: &mut Search) {
        let deadline = Instant::now() + Duration::from_secs(5);
        loop {
            let status = search.tick(10);
            if search.done.load(Ordering::Acquire)
                && !status.running
                && search.matcher.active_injectors() == 0
            {
                // An injector may finish just after the tick above sampled its
                // item count. Tick again after observing completion.
                if !search.tick(10).running {
                    break;
                }
            }
            assert!(Instant::now() < deadline, "Search stalled");
            thread::sleep(Duration::from_millis(5));
        }
    }
    fn names(search: &Search) -> BTreeSet<String> {
        search
            .matcher
            .snapshot()
            .matched_items(..)
            .map(|item| item.data.label.clone())
            .collect()
    }
    fn open(root: &Path, cache: &Path, all: bool) -> Search {
        Search::open(
            Policy::new(root.to_owned(), all, false),
            false,
            Some(cache.to_owned()),
        )
    }

    #[test]
    fn normal_search_respects_ignores_and_excludes_generated_artifacts() {
        let dir = tempfile::tempdir().unwrap();
        let cache = tempfile::tempdir().unwrap();
        fs::write(dir.path().join(".gitignore"), "ignored.pdf\n").unwrap();
        for name in [
            "notes.txt",
            "ignored.pdf",
            "weights.safetensors",
            "model.pth",
            "data.npy",
            "module.o",
        ] {
            fs::write(dir.path().join(name), "test").unwrap();
        }
        fs::create_dir(dir.path().join("node_modules")).unwrap();
        fs::write(dir.path().join("node_modules/dependency.txt"), "test").unwrap();
        let mut normal = open(dir.path(), cache.path(), false);
        finish(&mut normal);
        assert_eq!(names(&normal), BTreeSet::from(["notes.txt".to_owned()]));
        let mut all = open(dir.path(), cache.path(), true);
        finish(&mut all);
        assert_eq!(all.matcher.snapshot().item_count(), 8);
    }

    #[test]
    fn cache_reused_and_new_deleted_renamed_files_refresh_the_snapshot() {
        let root = tempfile::tempdir().unwrap();
        let cache = tempfile::tempdir().unwrap();
        fs::create_dir(root.path().join("nested")).unwrap();
        fs::write(root.path().join("nested/old.txt"), "test").unwrap();
        let mut cold = open(root.path(), cache.path(), false);
        finish(&mut cold);
        assert!(!cold.cached.load(Ordering::Acquire));
        let mut warm = open(root.path(), cache.path(), false);
        finish(&mut warm);
        assert!(warm.cached.load(Ordering::Acquire));
        assert_eq!(names(&cold), names(&warm));
        // ext4 timestamps may share a clock tick for very fast fixture writes.
        thread::sleep(Duration::from_millis(10));
        fs::rename(
            root.path().join("nested/old.txt"),
            root.path().join("nested/new.txt"),
        )
        .unwrap();
        fs::write(root.path().join("added.txt"), "test").unwrap();
        let mut changed = open(root.path(), cache.path(), false);
        finish(&mut changed);
        assert!(changed.cached.load(Ordering::Acquire));
        assert_eq!(
            names(&changed),
            BTreeSet::from(["nested/new.txt".to_owned(), "added.txt".to_owned()])
        );
        thread::sleep(Duration::from_millis(10));
        fs::remove_file(root.path().join("added.txt")).unwrap();
        let mut removed = open(root.path(), cache.path(), false);
        finish(&mut removed);
        assert_eq!(
            names(&removed),
            BTreeSet::from(["nested/new.txt".to_owned()])
        );
    }

    #[test]
    fn editing_ignore_in_place_invalidates_a_cached_search() {
        let root = tempfile::tempdir().unwrap();
        let cache = tempfile::tempdir().unwrap();
        fs::write(root.path().join(".gitignore"), "hidden.pdf\n").unwrap();
        fs::write(root.path().join("hidden.pdf"), "test").unwrap();
        let mut before = open(root.path(), cache.path(), false);
        finish(&mut before);
        assert_eq!(before.matcher.snapshot().item_count(), 0);
        fs::write(root.path().join(".gitignore"), "# visible now\n").unwrap();
        let mut after = open(root.path(), cache.path(), false);
        finish(&mut after);
        assert_eq!(names(&after), BTreeSet::from(["hidden.pdf".to_owned()]));
    }

    #[test]
    fn personal_scope_omits_application_data_and_keeps_user_documents() {
        let root = tempfile::tempdir().unwrap();
        for folder in ["Documents", "Games", ".local/share", ".dotfiles"] {
            fs::create_dir_all(root.path().join(folder)).unwrap();
            fs::write(root.path().join(folder).join("notes.txt"), "test").unwrap();
        }
        let policy = Policy {
            root: root.path().to_owned(),
            all: false,
            personal: true,
            roots: vec![root.path().join("Documents"), root.path().join(".dotfiles")],
            ignore: root.path().join("ignore"),
            key: 42,
        };
        let result = scan(&policy, &AtomicBool::new(false), |_| {}).unwrap();
        assert_eq!(result.files.len(), 2);
        assert!(result
            .files
            .iter()
            .all(|p| p.starts_with(root.path().join("Documents"))
                || p.starts_with(root.path().join(".dotfiles"))));
    }

    #[test]
    fn explicit_hidden_roots_work_and_symlink_directories_are_not_followed() {
        let root = tempfile::tempdir().unwrap();
        let cache = tempfile::tempdir().unwrap();
        let hidden = root.path().join(".config");
        fs::create_dir(&hidden).unwrap();
        fs::write(hidden.join("settings.txt"), "test").unwrap();
        std::os::unix::fs::symlink(&hidden, hidden.join("loop")).unwrap();
        let mut search = open(&hidden, cache.path(), false);
        finish(&mut search);
        assert_eq!(names(&search), BTreeSet::from(["settings.txt".to_owned()]));
    }
}
