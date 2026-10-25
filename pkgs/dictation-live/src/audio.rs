use rustfft::{Fft, FftPlanner, num_complex::Complex};
use std::{collections::VecDeque, sync::Arc};

pub const RATE: usize = 16_000;
pub const FRAME: usize = 256;
pub const BANDS: usize = 32;
// Keep uncertain audio between detected phrases. A 300 ms pre-roll loses
// softly spoken words when VAD is temporarily unsure; retain up to 20 s.
const PREFILL: usize = RATE * 20;
const HANGOVER: usize = RATE * 3 / 5;
const MAX_SEGMENT: usize = RATE * 24;
const OVERLAP: usize = RATE / 2;

pub struct Segment {
    pub index: usize,
    pub pcm: Vec<f32>,
    pub overlap: bool,
}

/// Retain phrase context and trailing consonants; close phrases at pauses.
/// Forced splits overlap by 500 ms, with text overlap reconciled on output.
pub struct Segmenter {
    vad: Box<earshot::Detector>,
    prefill: VecDeque<f32>,
    pcm: Vec<f32>,
    silence: usize,
    index: usize,
    overlap: bool,
    speech_frames: usize,
}

impl Segmenter {
    pub fn new() -> Self {
        Self {
            vad: earshot::Detector::default_boxed(),
            prefill: VecDeque::with_capacity(PREFILL),
            pcm: Vec::new(),
            silence: 0,
            index: 0,
            overlap: false,
            speech_frames: 0,
        }
    }

    pub fn feed(&mut self, frame: &[f32; FRAME]) -> Option<Segment> {
        let speech = self.vad.predict_f32(frame) >= 0.35;
        self.feed_classified(frame, speech)
    }

    fn feed_classified(&mut self, frame: &[f32], speech: bool) -> Option<Segment> {
        if self.pcm.is_empty() {
            if !speech {
                self.prefill.extend(frame);
                while self.prefill.len() > PREFILL {
                    self.prefill.pop_front();
                }
                return None;
            }
            self.pcm.extend(self.prefill.drain(..));
        }
        self.pcm.extend_from_slice(frame);
        if speech {
            self.speech_frames += 1;
            self.silence = 0;
        } else {
            self.silence += frame.len();
        }
        if self.silence >= HANGOVER {
            return self.finish();
        }
        if self.pcm.len() >= MAX_SEGMENT {
            let tail = self.pcm[self.pcm.len() - OVERLAP..].to_vec();
            let segment = self.finish();
            self.pcm = tail;
            self.overlap = true;
            // The overlap alone is not a new utterance if recording stops now.
            self.speech_frames = 0;
            return segment;
        }
        None
    }

    pub fn preview(&self) -> Option<Segment> {
        (self.speech_frames >= 3 && self.pcm.len() >= RATE / 2).then(|| Segment {
            index: self.index,
            pcm: self.pcm.clone(),
            overlap: self.overlap,
        })
    }

    pub fn finish(&mut self) -> Option<Segment> {
        let pcm = std::mem::take(&mut self.pcm);
        let valid = self.speech_frames >= 3;
        self.silence = 0;
        self.speech_frames = 0;
        if !valid {
            self.overlap = false;
            return None;
        }
        let segment = Segment {
            index: self.index,
            pcm,
            overlap: self.overlap,
        };
        self.index += 1;
        self.overlap = false;
        Some(segment)
    }
}

pub struct Spectrum {
    fft: Arc<dyn Fft<f32>>,
    samples: VecDeque<f32>,
    bins: Vec<Complex<f32>>,
    smoothed: [f32; BANDS],
}

impl Spectrum {
    pub fn new() -> Self {
        Self {
            fft: FftPlanner::new().plan_fft_forward(1024),
            samples: VecDeque::with_capacity(1024),
            bins: vec![Complex::default(); 1024],
            smoothed: [0.0; BANDS],
        }
    }

    pub fn feed(&mut self, samples: &[f32]) -> ([f32; BANDS], f32) {
        self.samples.extend(samples.iter().copied());
        while self.samples.len() > 1024 {
            self.samples.pop_front();
        }
        self.bins.fill(Complex::default());
        for (i, sample) in self.samples.iter().enumerate() {
            let window = 0.5 - 0.5 * (std::f32::consts::TAU * i as f32 / 1023.0).cos();
            self.bins[i].re = sample * window;
        }
        self.fft.process(&mut self.bins);
        for band in 0..BANDS {
            let low =
                (80.0 * 100.0_f32.powf(band as f32 / BANDS as f32) * 1024.0 / RATE as f32) as usize;
            let high = (80.0 * 100.0_f32.powf((band + 1) as f32 / BANDS as f32) * 1024.0
                / RATE as f32) as usize;
            let energy = self.bins[low.max(1)..high.max(low + 1).min(513)]
                .iter()
                .map(|value| value.norm())
                .fold(0.0_f32, f32::max)
                / 512.0;
            let level = ((20.0 * energy.max(1e-8).log10() + 70.0) / 70.0).clamp(0.0, 1.0);
            let smoothing = if level > self.smoothed[band] {
                0.7
            } else {
                0.2
            };
            self.smoothed[band] += (level - self.smoothed[band]) * smoothing;
        }
        let rms = (samples.iter().map(|v| v * v).sum::<f32>() / samples.len().max(1) as f32).sqrt();
        (self.smoothed, 20.0 * rms.max(1e-6).log10())
    }
}

/// Only remove an exact word overlap at a forced audio split, never at pauses:
/// intentional repetitions such as “yes. yes.” must survive ordinary pauses.
pub fn append_text(previous: &str, next: &str, overlap: bool) -> String {
    let next = next.trim();
    if previous.is_empty() {
        return next.to_owned();
    }
    if next.is_empty() {
        return previous.to_owned();
    }
    let left: Vec<_> = previous.split_whitespace().collect();
    let right: Vec<_> = next.split_whitespace().collect();
    let canonical = |word: &str| {
        word.trim_matches(|c: char| !c.is_alphanumeric())
            .to_lowercase()
    };
    let matched = if overlap {
        (1..=left.len().min(right.len()).min(12))
            .rev()
            .find(|&count| {
                left[left.len() - count..]
                    .iter()
                    .zip(&right[..count])
                    .all(|(a, b)| canonical(a) == canonical(b))
            })
            .unwrap_or(0)
    } else {
        0
    };
    let tail = right[matched..].join(" ");
    if tail.is_empty() {
        previous.to_owned()
    } else {
        format!("{previous} {tail}")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn silence_does_not_generate_a_transcript() {
        let mut segmenter = Segmenter::new();
        for _ in 0..100 {
            assert!(segmenter.feed(&[0.0; FRAME]).is_none());
        }
        assert!(segmenter.finish().is_none());
    }
    #[test]
    fn retains_preroll_and_consonant_tail() {
        let mut s = Segmenter::new();
        for _ in 0..(PREFILL / FRAME + 1) {
            s.feed_classified(&[0.0; FRAME], false);
        }
        for _ in 0..40 {
            s.feed_classified(&[0.25; FRAME], true);
        }
        let mut result = None;
        for _ in 0..38 {
            if let Some(segment) = s.feed_classified(&[0.0; FRAME], false) {
                result = Some(segment);
            }
        }
        let pcm = result.unwrap().pcm;
        assert_eq!(pcm.iter().filter(|v| **v == 0.25).count(), 40 * FRAME);
        assert!(pcm.len() >= PREFILL + 40 * FRAME + HANGOVER);
        assert!(s.finish().is_none());
    }
    #[test]
    fn overlap_does_not_repeat_words_or_remove_deliberate_repetition() {
        assert_eq!(
            append_text("Vi bruger DDPM", "ddpm og iMF.", true),
            "Vi bruger DDPM og iMF."
        );
        assert_eq!(append_text("yes.", "Yes.", false), "yes. Yes.");
    }
    #[test]
    fn real_fft_distinguishes_low_and_high_frequency() {
        fn peak(hz: f32) -> usize {
            let mut spectrum = Spectrum::new();
            let samples: Vec<_> = (0..1024)
                .map(|i| 0.3 * (std::f32::consts::TAU * hz * i as f32 / RATE as f32).sin())
                .collect();
            let (bands, _) = spectrum.feed(&samples);
            bands
                .iter()
                .enumerate()
                .max_by(|a, b| a.1.total_cmp(b.1))
                .unwrap()
                .0
        }
        assert!(peak(250.0) + 8 < peak(4000.0));
    }
}
