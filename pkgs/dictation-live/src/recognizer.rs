use anyhow::{Context, Result};
use std::{env, path::PathBuf};
use transcribe_cpp::{Model, RunOptions, Session};

pub struct Recognizer {
    session: Session,
    pub backend: String,
}

pub fn load() -> Result<Recognizer> {
    transcribe_cpp::init_logging();
    let backend_dir =
        env::var("DICTATION_BACKEND_DIR").context("DICTATION_BACKEND_DIR is unset")?;
    transcribe_cpp::init_backends(backend_dir)?;
    let path = env::var_os("DICTATION_MODEL_PATH")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            PathBuf::from(env::var_os("HOME").unwrap_or_default())
                .join(".local/share/com.pais.handy/models/parakeet-ultra-Q8_0.gguf")
        });
    let model = Model::load(&path).with_context(|| format!("Loading {}", path.display()))?;
    let device = model.device()?;
    eprintln!(
        "dictation-live: recognition backend {} ({})",
        device.name, device.description
    );
    Ok(Recognizer {
        session: model.session()?,
        backend: device.name,
    })
}

pub fn transcribe(recognizer: &mut Recognizer, pcm: &[f32]) -> Result<String> {
    Ok(recognizer
        .session
        .run(pcm, &RunOptions::default())?
        .text
        .trim()
        .to_owned())
}
