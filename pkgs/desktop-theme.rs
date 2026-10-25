// Included by personal Rust tools. No new dependencies beyond serde_json.
#[allow(dead_code)]
mod desktop_theme {
    use std::{cell::RefCell, path::PathBuf, time::{Duration, Instant}};

    pub fn config(name: &str) -> PathBuf {
        let root = std::env::var_os("XDG_CONFIG_HOME").map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from(std::env::var_os("HOME").unwrap_or_default()).join(".config"));
        root.join("dotfiles-theme/current").join(name)
    }

    #[derive(Clone)]
    pub struct Palette {
        pub base: [u8; 3], pub surface: [u8; 3], pub overlay: [u8; 3],
        pub text: [u8; 3], pub muted: [u8; 3], pub accent: [u8; 3],
        pub red: [u8; 3], pub green: [u8; 3], pub yellow: [u8; 3],
    }
    impl Default for Palette {
        fn default() -> Self {
            Self { base:[30,30,46], surface:[49,50,68], overlay:[69,71,90],
                text:[205,214,244], muted:[166,173,200], accent:[203,166,247],
                red:[243,139,168], green:[166,227,161], yellow:[249,226,175] }
        }
    }
    fn read() -> Palette {
        let mut p = Palette::default();
        if let Ok(text) = std::fs::read_to_string(config("colors.json")) {
            if let Ok(json) = serde_json::from_str::<serde_json::Value>(&text) {
                for (name, target) in [("base",&mut p.base),("surface",&mut p.surface),
                    ("overlay",&mut p.overlay),("text",&mut p.text),("muted",&mut p.muted),
                    ("accent",&mut p.accent),("red",&mut p.red),("green",&mut p.green),("yellow",&mut p.yellow)] {
                    if let Some(hex) = json[name].as_str().and_then(|s| s.strip_prefix('#')) {
                        if hex.len() == 6 {
                            if let Ok(rgb) = u32::from_str_radix(hex,16) {
                                *target = [(rgb>>16) as u8,(rgb>>8) as u8,rgb as u8];
                            }
                        }
                    }
                }
            }
        }
        p
    }
    thread_local! { static CACHE: RefCell<(Instant, Palette)> = RefCell::new((Instant::now(), read())); }
    pub fn palette() -> Palette {
        CACHE.with(|cache| {
            let mut cache = cache.borrow_mut();
            if cache.0.elapsed() >= Duration::from_millis(100) { *cache = (Instant::now(),read()); }
            cache.1.clone()
        })
    }
}
