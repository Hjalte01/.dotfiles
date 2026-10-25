use crate::{
    audio::{BANDS, FRAME, RATE, Segment, Segmenter, Spectrum, append_text},
    recognizer,
};
use anyhow::{Context, Result, bail};
use std::{
    collections::VecDeque,
    fs::{self, OpenOptions},
    io::{Read, Write},
    os::unix::fs::{OpenOptionsExt, PermissionsExt},
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::{
        Arc, Condvar, Mutex, MutexGuard,
        atomic::{AtomicBool, AtomicU64, Ordering},
    },
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

pub fn lock<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    mutex.lock().unwrap_or_else(|error| error.into_inner())
}

#[derive(Clone, Copy, PartialEq)]
pub enum Phase {
    Hidden,
    Arming,
    Listening,
    Finishing,
    Done,
    Error,
}

#[derive(Clone)]
pub struct View {
    pub phase: Phase,
    pub text: String,
    pub status: String,
    pub bands: [f32; BANDS],
    pub db: f32,
    pub started: Instant,
    pub hide_at: Option<Instant>,
    pub ready: bool,
    pub first_preview: Option<Duration>,
    pub stop_requested: Option<Instant>,
}

impl Default for View {
    fn default() -> Self {
        Self {
            phase: Phase::Hidden,
            text: String::new(),
            status: String::new(),
            bands: [0.0; BANDS],
            db: -120.0,
            started: Instant::now(),
            hide_at: None,
            ready: false,
            first_preview: None,
            stop_requested: None,
        }
    }
}

struct Work {
    generation: u64,
    final_jobs: VecDeque<Segment>,
    preview: Option<Segment>,
    finishing: bool,
    insert: bool,
    full_audio: Option<Vec<f32>>,
}

pub struct Shared {
    pub view: Mutex<View>,
    queue: Mutex<Work>,
    wake: Condvar,
    pub generation: AtomicU64,
}

impl Shared {
    pub fn new() -> Arc<Self> {
        Arc::new(Self {
            view: Mutex::new(View::default()),
            queue: Mutex::new(Work {
                generation: 0,
                final_jobs: VecDeque::new(),
                preview: None,
                finishing: false,
                insert: true,
                full_audio: None,
            }),
            wake: Condvar::new(),
            generation: AtomicU64::new(0),
        })
    }

    fn submit(&self, generation: u64, segment: Segment, final_chunk: bool) {
        let mut queue = lock(&self.queue);
        if queue.generation != generation {
            return;
        }
        if final_chunk {
            if queue
                .preview
                .as_ref()
                .is_some_and(|preview| preview.index <= segment.index)
            {
                queue.preview = None;
            }
            queue.final_jobs.push_back(segment);
        } else {
            queue.preview = Some(segment);
        }
        self.wake.notify_one();
    }

    fn finish(&self, generation: u64, pcm: Vec<f32>) {
        let mut queue = lock(&self.queue);
        if queue.generation == generation {
            queue.preview = None;
            queue.finishing = true;
            queue.full_audio = Some(pcm);
            self.wake.notify_one();
        }
    }

    pub fn error(&self, message: String) {
        eprintln!("dictation-live: {message}");
        let mut view = lock(&self.view);
        view.phase = Phase::Error;
        view.status = message;
        view.hide_at = Some(Instant::now() + Duration::from_secs(12));
    }
}

enum Task {
    Final(u64, Segment),
    Preview(u64, Segment),
    Finish(u64, bool, Vec<f32>),
}

pub fn start_worker(shared: Arc<Shared>) {
    thread::spawn(move || {
        let mut session = match recognizer::load() {
            Ok(session) => session,
            Err(error) => {
                shared.error(format!("Could not load speech model: {error:#}"));
                return;
            }
        };
        lock(&shared.view).ready = true;
        let mut rules = match dictation::load_rules() {
            Ok(rules) => rules,
            Err(error) => {
                shared.error(format!("Dictionary error: {error}"));
                return;
            }
        };
        let mut generation = 0;
        let mut committed = String::new();
        let mut failed = false;
        loop {
            let task = {
                let mut queue = lock(&shared.queue);
                loop {
                    let current = queue.generation;
                    if let Some(segment) = queue.final_jobs.pop_front() {
                        break Task::Final(current, segment);
                    }
                    if queue.finishing {
                        queue.finishing = false;
                        let pcm = queue.full_audio.take().unwrap_or_default();
                        break Task::Finish(current, queue.insert, pcm);
                    }
                    if let Some(segment) = queue.preview.take() {
                        break Task::Preview(current, segment);
                    }
                    queue = shared
                        .wake
                        .wait(queue)
                        .unwrap_or_else(|error| error.into_inner());
                }
            };
            let current = match &task {
                Task::Final(g, _) | Task::Preview(g, _) | Task::Finish(g, _, _) => *g,
            };
            if current != shared.generation.load(Ordering::SeqCst) {
                continue;
            }
            if generation != current {
                generation = current;
                committed.clear();
                failed = false;
                match dictation::load_rules() {
                    Ok(updated) => rules = updated,
                    Err(error) => {
                        shared.error(format!("Dictionary error: {error}"));
                        failed = true;
                    }
                }
            }
            let is_final = matches!(&task, Task::Final(_, _));
            match task {
                Task::Final(_, segment) | Task::Preview(_, segment) => {
                    let text = match recognizer::transcribe(&mut session, &segment.pcm) {
                        Ok(text) => text,
                        Err(error) => {
                            if current == shared.generation.load(Ordering::SeqCst) && is_final {
                                failed = true;
                                shared.error(format!("Recognition failed: {error:#}"));
                            }
                            continue;
                        }
                    };
                    if current != shared.generation.load(Ordering::SeqCst) {
                        continue;
                    }
                    let joined = append_text(&committed, &text, segment.overlap);
                    if is_final {
                        committed = joined.clone();
                    }
                    let corrected = dictation::normalize(&joined, &rules);
                    let tail: String = corrected
                        .chars()
                        .rev()
                        .take(950)
                        .collect::<Vec<_>>()
                        .into_iter()
                        .rev()
                        .collect();
                    let mut view = lock(&shared.view);
                    if !tail.is_empty() && view.first_preview.is_none() {
                        let elapsed = view.started.elapsed();
                        view.first_preview = Some(elapsed);
                        eprintln!("dictation-live: first preview {} ms", elapsed.as_millis());
                    }
                    view.text = tail;
                }
                Task::Finish(_, insert, pcm) => {
                    if failed {
                        continue;
                    }
                    // Preview segmentation must never reduce final accuracy.
                    // Decode all captured audio once, preserving soft speech
                    // and context that VAD/phrase boundaries can miss.
                    if !committed.is_empty() && !pcm.is_empty() {
                        match recognizer::transcribe(&mut session, &pcm) {
                            Ok(text) => committed = text,
                            Err(error) => {
                                shared.error(format!("Final recognition failed: {error:#}"));
                                continue;
                            }
                        }
                        if current != shared.generation.load(Ordering::SeqCst) {
                            continue;
                        }
                        let corrected = dictation::normalize(&committed, &rules);
                        lock(&shared.view).text = corrected
                            .chars()
                            .rev()
                            .take(950)
                            .collect::<Vec<_>>()
                            .into_iter()
                            .rev()
                            .collect();
                    }
                    if insert
                        && !committed.trim().is_empty()
                        && let Err(error) = paste(&committed)
                    {
                        let saved = save_unsent(&committed)
                            .map(|path| path.display().to_string())
                            .unwrap_or_else(|_| "could not save a draft".into());
                        shared.error(format!("Could not paste: {error}. Draft: {saved}"));
                        continue;
                    }
                    if current == shared.generation.load(Ordering::SeqCst) {
                        let mut view = lock(&shared.view);
                        view.phase = Phase::Done;
                        if let Some(stopped) = view.stop_requested {
                            eprintln!(
                                "dictation-live: completion after stop {} ms",
                                stopped.elapsed().as_millis()
                            );
                        }
                        view.status = if !insert {
                            "Replay finished · nothing inserted".into()
                        } else if committed.is_empty() {
                            "No speech detected".into()
                        } else {
                            "Inserted".into()
                        };
                        view.hide_at = Some(Instant::now() + Duration::from_millis(900));
                    }
                }
            }
        }
    });
}

fn paste(text: &str) -> Result<()> {
    let mut child = Command::new("dictation")
        .arg("paste")
        .stdin(Stdio::piped())
        .spawn()?;
    child
        .stdin
        .take()
        .context("No paste input")?
        .write_all(text.as_bytes())?;
    if !child.wait()?.success() {
        bail!("text insertion failed");
    }
    Ok(())
}

fn save_unsent(text: &str) -> Result<PathBuf> {
    let base = std::env::var_os("XDG_CACHE_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            PathBuf::from(std::env::var_os("HOME").unwrap_or_default()).join(".cache")
        });
    let directory = base.join("dictation/unsent");
    fs::create_dir_all(&directory)?;
    fs::set_permissions(&directory, fs::Permissions::from_mode(0o700))?;
    let stamp = SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos();
    let path = directory.join(format!("{stamp}.txt"));
    OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(&path)?
        .write_all(text.as_bytes())?;
    Ok(path)
}

struct Capture {
    child: Option<Arc<Mutex<Child>>>,
    cancelled: Arc<AtomicBool>,
    stopped: Arc<AtomicBool>,
    finished: Arc<AtomicBool>,
}

pub struct Controller {
    pub shared: Arc<Shared>,
    capture: Option<Capture>,
}

impl Controller {
    pub fn new(shared: Arc<Shared>) -> Self {
        Self {
            shared,
            capture: None,
        }
    }

    pub fn toggle(&mut self) -> Result<()> {
        if self
            .capture
            .as_ref()
            .is_some_and(|capture| capture.finished.load(Ordering::SeqCst))
        {
            self.capture = None;
        }
        if let Some(capture) = self.capture.take() {
            capture.stopped.store(true, Ordering::SeqCst);
            if let Some(child) = &capture.child {
                lock(child).kill().ok();
            }
            let mut view = lock(&self.shared.view);
            if matches!(view.phase, Phase::Listening | Phase::Arming) {
                view.stop_requested = Some(Instant::now());
                view.phase = Phase::Finishing;
                view.status = "Finishing transcript…".into();
            }
            return Ok(());
        }
        self.start(None)
    }

    pub fn replay(&mut self, path: &std::path::Path) -> Result<()> {
        if matches!(
            lock(&self.shared.view).phase,
            Phase::Arming | Phase::Listening | Phase::Finishing
        ) {
            bail!("Finish or cancel the current dictation first");
        }
        self.start(Some(path))
    }

    fn start(&mut self, replay: Option<&std::path::Path>) -> Result<()> {
        if lock(&self.shared.view).phase == Phase::Finishing {
            return Ok(());
        }
        if !lock(&self.shared.view).ready {
            bail!("Speech model is still loading; try again in a moment");
        }
        let is_replay = replay.is_some();
        let (reader, child): (Box<dyn Read + Send>, _) = if let Some(path) = replay {
            (Box::new(WavInput::open(path)?), None)
        } else {
            let mut command = Command::new("pw-record");
            command.args([
                "--raw",
                "--rate=16000",
                "--channels=1",
                "--format=f32",
                "--latency=32ms",
                "--media-role=Communication",
            ]);
            if let Ok(target) = std::env::var("DICTATION_AUDIO_TARGET") {
                command.arg("--target").arg(target);
            }
            let mut child = command
                .arg("-")
                .stdout(Stdio::piped())
                .stderr(Stdio::inherit())
                .spawn()
                .context("Could not start PipeWire microphone capture")?;
            let reader = child.stdout.take().context("No microphone stream")?;
            (Box::new(reader), Some(Arc::new(Mutex::new(child))))
        };
        let generation = self.shared.generation.fetch_add(1, Ordering::SeqCst) + 1;
        {
            let mut queue = lock(&self.shared.queue);
            queue.generation = generation;
            queue.final_jobs.clear();
            queue.preview = None;
            queue.finishing = false;
            queue.full_audio = None;
            queue.insert = !is_replay;
        }
        {
            let mut view = lock(&self.shared.view);
            *view = View {
                phase: Phase::Arming,
                status: if is_replay {
                    "Starting replay…".into()
                } else {
                    "Starting microphone…".into()
                },
                ready: true,
                ..View::default()
            };
        }
        let capture = Capture {
            child,
            cancelled: Arc::new(AtomicBool::new(false)),
            stopped: Arc::new(AtomicBool::new(false)),
            finished: Arc::new(AtomicBool::new(false)),
        };
        let shared = Arc::clone(&self.shared);
        let child = capture.child.clone();
        let cancelled = Arc::clone(&capture.cancelled);
        let stopped = Arc::clone(&capture.stopped);
        let finished = Arc::clone(&capture.finished);
        thread::spawn(move || {
            let outcome =
                capture_audio(reader, &shared, generation, &cancelled, &stopped, is_replay);
            if let Some(child) = child {
                lock(&child).kill().ok();
                lock(&child).wait().ok();
            }
            finished.store(true, Ordering::SeqCst);
            if cancelled.load(Ordering::SeqCst)
                || shared.generation.load(Ordering::SeqCst) != generation
            {
                return;
            }
            let pcm = match outcome {
                Ok(pcm) => pcm,
                Err(error) => {
                    shared.error(format!("Microphone error: {error:#}"));
                    return;
                }
            };
            if !is_replay && !stopped.load(Ordering::SeqCst) {
                shared.error("Microphone disconnected; dictation was not inserted".into());
                return;
            }
            {
                let mut view = lock(&shared.view);
                if matches!(view.phase, Phase::Listening | Phase::Arming) {
                    view.stop_requested.get_or_insert_with(Instant::now);
                    view.phase = Phase::Finishing;
                    view.status = "Finishing transcript…".into();
                }
            }
            shared.finish(generation, pcm);
        });
        self.capture = Some(capture);
        Ok(())
    }

    pub fn cancel(&mut self) {
        let generation = self.shared.generation.fetch_add(1, Ordering::SeqCst) + 1;
        if let Some(capture) = self.capture.take() {
            capture.cancelled.store(true, Ordering::SeqCst);
            if let Some(child) = &capture.child {
                lock(child).kill().ok();
            }
        }
        let mut queue = lock(&self.shared.queue);
        queue.generation = generation;
        queue.final_jobs.clear();
        queue.preview = None;
        queue.finishing = false;
        queue.full_audio = None;
        lock(&self.shared.view).phase = Phase::Hidden;
    }

    pub fn poll(&mut self) {
        let message = {
            let view = lock(&self.shared.view);
            (view.phase == Phase::Error && self.capture.is_some()).then(|| view.status.clone())
        };
        if let Some(message) = message {
            self.cancel();
            self.shared.error(message);
        }
        if self
            .capture
            .as_ref()
            .is_some_and(|capture| capture.finished.load(Ordering::SeqCst))
        {
            self.capture = None;
        }
    }
}

fn capture_audio(
    mut reader: impl Read,
    shared: &Shared,
    generation: u64,
    cancelled: &AtomicBool,
    stopped: &AtomicBool,
    replay: bool,
) -> Result<Vec<f32>> {
    let mut bytes = [0_u8; FRAME * 4];
    let mut segmenter = Segmenter::new();
    let mut spectrum = Spectrum::new();
    let mut next_preview = RATE;
    let mut total = 0;
    let mut received = false;
    let mut full_audio = Vec::new();
    let started = Instant::now();
    loop {
        if replay && stopped.load(Ordering::SeqCst) {
            break;
        }
        let mut filled = 0;
        while filled < bytes.len() {
            let count = reader.read(&mut bytes[filled..])?;
            if count == 0 {
                break;
            }
            filled += count;
        }
        if filled == 0 {
            break;
        }
        if cancelled.load(Ordering::SeqCst)
            || generation != shared.generation.load(Ordering::SeqCst)
        {
            return Ok(Vec::new());
        }
        let mut frame = [0.0; FRAME];
        for (sample, bytes) in frame
            .iter_mut()
            .zip(bytes[..filled - filled % 4].chunks_exact(4))
        {
            *sample = f32::from_le_bytes(bytes.try_into()?).clamp(-1.0, 1.0);
            if !sample.is_finite() {
                bail!("Invalid microphone sample");
            }
        }
        received = true;
        full_audio.extend_from_slice(&frame);
        total += FRAME;
        let (bands, db) = spectrum.feed(&frame);
        {
            let mut view = lock(&shared.view);
            if view.phase == Phase::Arming {
                view.phase = Phase::Listening;
                view.status = if replay {
                    "Replay · microphone off".into()
                } else {
                    "Listening".into()
                };
            }
            view.bands = bands;
            view.db = db;
        }
        if let Some(segment) = segmenter.feed(&frame) {
            shared.submit(generation, segment, true);
        }
        if total >= next_preview {
            next_preview = total + RATE * 4 / 5;
            if let Some(segment) = segmenter.preview() {
                shared.submit(generation, segment, false);
            }
        }
        if filled < bytes.len() {
            break;
        }
        if replay {
            let deadline = started + Duration::from_secs_f64(total as f64 / RATE as f64);
            if let Some(delay) = deadline.checked_duration_since(Instant::now()) {
                thread::sleep(delay);
            }
        }
    }
    if !received {
        bail!("No audio received; check the default microphone");
    }
    if let Some(segment) = segmenter.finish() {
        shared.submit(generation, segment, true);
    }
    Ok(full_audio)
}

struct WavInput(hound::WavReader<std::io::BufReader<std::fs::File>>);

impl WavInput {
    fn open(path: &std::path::Path) -> Result<Self> {
        let reader = hound::WavReader::open(path)?;
        let spec = reader.spec();
        anyhow::ensure!(
            spec.channels == 1
                && spec.sample_rate == RATE as u32
                && spec.bits_per_sample == 16
                && spec.sample_format == hound::SampleFormat::Int,
            "Replay expects mono 16 kHz PCM16 WAV"
        );
        Ok(Self(reader))
    }
}

impl Read for WavInput {
    fn read(&mut self, output: &mut [u8]) -> std::io::Result<usize> {
        let mut written = 0;
        for chunk in output.chunks_exact_mut(4) {
            let Some(sample) = self.0.samples::<i16>().next() else {
                break;
            };
            let value = sample.map_err(std::io::Error::other)? as f32 / 32768.0;
            chunk.copy_from_slice(&value.to_le_bytes());
            written += 4;
        }
        Ok(written)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn segment(index: usize) -> Segment {
        Segment {
            index,
            pcm: vec![0.1; FRAME],
            overlap: false,
        }
    }
    #[test]
    fn previews_coalesce_and_final_chunks_are_never_overwritten() {
        let shared = Shared::new();
        shared.submit(0, segment(0), false);
        shared.submit(0, segment(1), false);
        assert_eq!(lock(&shared.queue).preview.as_ref().unwrap().index, 1);
        shared.submit(0, segment(0), true);
        shared.submit(0, segment(1), true);
        let queue = lock(&shared.queue);
        assert_eq!(
            queue.final_jobs.iter().map(|s| s.index).collect::<Vec<_>>(),
            vec![0, 1]
        );
        assert!(queue.preview.is_none());
    }
    #[test]
    fn cancellation_invalidates_queued_audio_and_late_results() {
        let shared = Shared::new();
        shared.submit(0, segment(0), true);
        let mut controller = Controller::new(Arc::clone(&shared));
        controller.cancel();
        shared.submit(0, segment(1), true);
        shared.finish(0, vec![0.1; FRAME]);
        let queue = lock(&shared.queue);
        assert!(queue.final_jobs.is_empty());
        assert!(!queue.finishing);
        assert_eq!(queue.generation, 1);
    }
}
