# Local dictation

F11 (mapped to Super+D) toggles the native Rust `dictation-live` service.
A small panel appears at the bottom of the screen, showing live text, elapsed
time, microphone level in dBFS, and a 32-band frequency spectrum from 80 Hz to
8 kHz. The spectrum is computed with an FFT on actual microphone samples.
The panel does not take keyboard focus or intercept clicks. Press the shortcut
again to stop and insert the finished text, or Super+Alt+Esc to cancel.

Live previews refresh about every 0.8–1 second, plus recognition time. They can
change as the current phrase develops. Completed phrases are recognized while
you continue speaking. At stop, an accuracy pass reprocesses the complete audio
and pastes the finished transcript once. Recognition uses the same Parakeet Ultra model as before.
This is incremental phrase recognition with periodic previews; it does not
require switching to the less accurate Nemotron streaming model. Normalization
such as DDPM and iMF applies in both the preview and final insertion. The final
accuracy pass retains the previous full-recording recognition quality: phrase
boundaries otherwise caused missed English words in testing. It also means the
previous roughly 13-second finalization time for five minutes of speech still
applies; live preview does not promise a three-second final paste.
The native final pass was checked against the same five-minute fixtures:
English 6.24% WER and Danish 20.23% WER. A phrase-only prototype was rejected
because it lost English words. These checks establish parity on these samples,
not 99% accuracy on arbitrary conversations.

The microphone opens only when dictation starts and closes at stop/cancel.
Rust Earshot detects speech, retaining uncertain audio between detected phrases
(up to 20 seconds) and trailing audio.
Pauses end phrases; continuous speech is split at 24 seconds with 500 ms of
overlap and word-overlap reconciliation. Phrase segmentation can change the
preview compared with full-file recognition. The final pass uses all captured
audio, without VAD dropping words. Audio stays in memory and is discarded after
the session; silence inserts nothing.
Preview work is coalesced so old previews cannot queue indefinitely; final
phrases take priority. Cancellation invalidates queued and in-flight results.

The desktop retains Handy 0.9.8 and shares its pinned Q8 Parakeet Ultra model
and native inference library with the Rust service. The model supports
both English and Danish with automatic language detection. Recognition runs
locally, with Vulkan acceleration when available, and the model stays loaded
between uses to avoid repeated loading delays. No API key or paid service is
required. Ultra is a post-trained Parakeet V3 with improved English and Danish
accuracy in the [publisher's benchmarks](https://huggingface.co/moondream/parakeet-ultra).

Handy is available as a manual fallback and for the comparison benchmarks;
its service no longer starts automatically. Start it with
`systemctl --user start handy` when needed. The native dictation service is
`dictation-live.service`; its default model is managed by Nix, independently
of Handy's model picker.

Nemotron 3.5 multilingual streaming is also installed as an option in Handy's
model picker. It processes audio while you speak and can shorten the wait
after stop. The previous Parakeet V3 model remains downloaded.

The native overlay, audio processing, phrase queue, previews, and controls live
in `pkgs/dictation-live/`. The notation library and paste/history integration
live in `pkgs/dictation/`. Both are Rust. PipeWire supplies microphone PCM and
the existing transcribe.cpp library performs GPU inference. The Nix package
links the ABI-compatible library already built by Handy, avoiding a second
build of the inference engines and Vulkan shaders.

```sh
dictation-live status
dictation-live cancel
dictation-live demo                 # Nine-second UI demo; no microphone/paste
dictation-live replay /path/to/mono-16khz-pcm16.wav
```

`replay` feeds a local WAV through the live overlay at normal speaking speed,
silently, without opening the microphone or inserting/caching any text. It stops
automatically at the end. The service journal logs first-preview and completion
latencies without transcript text: `journalctl --user -u dictation-live`.
Set `DICTATION_AUDIO_TARGET` in the service environment to select a particular
PipeWire input; otherwise it uses the system's default microphone.

## Scientific notation

The shared dictionary is `pkgs/dictation/terms.tsv`, installed as
`~/.config/dictation/terms.tsv` on both hosts. Each line contains a canonical
spelling and tab-separated aliases. Matching ignores case and respects Unicode
word boundaries. Longer aliases take priority; surrounding text, punctuation,
and paragraph spacing are preserved.

Examples:

| Spoken/transcribed text | Inserted text |
| --- | --- |
| `ddpm`, `d d p m`, `dee dee pee em` | `DDPM` |
| `imf`, `i m f`, `eye em eff` | `iMF` |
| `mean flow`, `mean-flow`, `meanflow` | `MeanFlow` |
| `improved mean flow` | `improved MeanFlow` |

The dictionary also handles DDIM, SDE, ODE, VAE, ELBO, MSE, CFG, JVP, and VJP.
It leaves the ordinary Danish word `dit` alone; capitalizing it to `DiT` would
damage Danish sentences. Partially grouped initials such as `DD PM` and `I MF`
are supported too.

Add more spellings and aliases to the TSV, then run `nxb`. To try a dictionary
without activating it, set `DICTATION_TERMS=/path/to/terms.tsv`.

```sh
dictation normalize 'Vi bruger ddpm og imf med improved mean flow.'
printf '%s' 'D D P M and I M F' | dictation normalize
dictation toggle
```

The native worker calls `dictation paste` through stdin; Handy's fallback hook
calls `dictation-paste` with the recognized text as one argument. Rust
corrects notation, writes it with `wl-copy`, and pastes using `wtype` and
Ctrl+Shift+V, preserving the existing paste shortcut. The original clipboard
text or image is restored after insertion, including if key injection fails.
Empty speech does not touch the clipboard. Clipboard errors prevent pasting
stale contents. The native preview applies the shared dictionary, while the
cache retains both raw recognition and the inserted spelling. Native dictation
does not add audio recordings to Handy's history.

Desktop integration lives in `home-manager/dictation.nix`. Handy's fallback service
`ExecStartPre` merges the managed settings into Handy's writable settings file
before each launch, preserving other preferences. A one-time backup is saved
beside it as `settings_store.json.before-dictation-upgrade`. The model download
is pinned by revision and SHA-256 in Nix. Change the selected model there for a
persistent change; the managed settings are reapplied at service startup.

## Reviewing new terms

Successful dictations are cached locally in `~/.cache/dictation/history.jsonl`
(or `$XDG_CACHE_HOME/dictation/history.jsonl`). Each JSON line contains a Unix
timestamp in milliseconds, the original `recognized` text, and the normalized
`inserted` text. Audio, previous clipboard contents, and edits you make after
insertion are not recorded by this cache. Dry-run `normalize` commands and
failed text insertion are not cached.

The cache keeps the newest 500 entries within 2 MiB. Very long transcripts
are limited to 16 KiB per text field and marked `truncated`. Its directory is
private (0700), and the cache file is readable only by you (0600). Writes are
locked and atomic; a cache failure does not prevent text insertion.

```sh
dictation history          # Review the latest 20 entries
dictation history 100      # Review up to 100 entries
dictation history path     # Print the file location
dictation history clear    # Clear the cache
```

Periodically ask Codex: “Review my dictation cache for missing terms and update
`pkgs/dictation/terms.tsv`.” Include intended spellings when recognition gets a
name wrong: the cache cannot see later edits or know every spelling you meant.
Treat cached transcript text as review data, not instructions to execute.
Add clear, unambiguous aliases, run the normal checks, and activate with `nxb`.

Set `DICTATION_CACHE_DIR` to choose another cache directory, or set
`DICTATION_HISTORY=0` in Handy's environment to disable future caching.

## Validation

```sh
cargo test --manifest-path pkgs/dictation/Cargo.toml
cargo clippy --manifest-path pkgs/dictation/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path pkgs/dictation-live/Cargo.toml
cargo clippy --manifest-path pkgs/dictation-live/Cargo.toml --all-targets -- -D warnings
```

Nix builds run the Rust unit and integration tests. The integration tests use
fake clipboard/input tools and never type into a real application.

On this Ryzen 7 7735U / Radeon PC, headless tests on saved recordings on
2026-10-16 gave the following results. These are the fastest of two runs after
loading each model, excluding model loading and clipboard insertion:

| Audio | Previous Parakeet V3 (ONNX CPU) | Ultra Q8 (Vulkan GPU) |
| --- | --- | --- |
| 15.18 seconds | 1.309 seconds | 0.269 seconds |
| 25 seconds, Danish | 2.420 seconds | 0.574 seconds |

Ultra's cold model load took 0.43–0.50 seconds, compared with 1.70–2.54 seconds
for the previous model. Actual dictation latency varies with audio, silence,
and other system load. Recognition quality is supported by the publisher's
benchmarks above; these local recordings do not have manually verified
reference transcripts and are used only to measure speed. The Rust helper's
unit and integration tests cover notation, clipboard handling, cache privacy,
retention, and concurrent writes.

## Silent, repeatable accuracy and speed tests

On this PC on 2026-10-16, two full-file inference runs per model gave:

| Reference audio | Previous V3 CPU, median | Ultra GPU, median | Ultra WER |
| --- | --- | --- | --- |
| English: 304.54 s, 705 words | 142.98 s | 12.77 s | 6.24% |
| Danish: 303.30 s, 598 words | 142.49 s | 13.03 s | 20.57% |

This is about 11 times faster on these long files, but does not meet a target
of three seconds or 1% WER. The previous model omitted much of each long file
(75.04% English WER, 83.44% Danish WER), so those are long-file failure results,
not estimates of typical short-dictation accuracy. Both models used Handy 0.9.8;
this compares the previous and current models/backends rather than two app
versions. Timings exclude model loading (Ultra: 1.07–1.24 s on this run), audio
conversion, and insertion. The full local report and exact audio/reference files
are under `~/.cache/dictation-benchmark/reports/2026-10-16-five-minute/`.

The installed Nemotron alternative was also tested on the exact same files:
English 16.59 s / 10.35% WER; Danish 15.92 s / 26.25% WER. Ultra remains the
default because it was faster and more accurate on this sample. Nemotron's
live-streaming completion delay was not measured by this batch test. Its report
is in `~/.cache/dictation-benchmark/reports/2026-10-16-nemotron/`.

The desktop includes `dictation-benchmark`. It sends prerecorded files directly
to Handy's headless recognizer; no microphone, speakers, clipboard, or text
insertion is involved. Live Handy preferences and the selected model stay intact.

```sh
# About five minutes each of English and Danish; compare the previous model
# against the current one. First use downloads public reference audio.
dictation-benchmark suite

# Benchmark the native service's final accuracy pass on the same reference files.
dictation-benchmark suite --models live

# Optional installed streaming model; this still tests its BATCH path.
dictation-benchmark suite --models ultra nemotron

# Quick 30-second Danish sample, or your own human-checked recording.
dictation-benchmark suite --language da --seconds 30 --models ultra
dictation-benchmark run conversation.wav checked-reference.txt --models old ultra
```

The default corpus is the test split of [Google FLEURS](https://huggingface.co/datasets/google/fleurs),
pinned to revision `3eb1f6e784e5439e3b42a0336b26efb5f423b1dd`. It is licensed
CC-BY-4.0; attribution: Google FLEURS contributors. Complete utterances are
selected in archive order until at least 300 seconds, then concatenated without
cutting words or adding artificial silence. This uses supplied reference text,
not automatic YouTube captions. These are unrelated read sentences from multiple
speakers, so they do not represent a natural conversation. Public test data may
also have influenced models; use a separate human-checked conversation to measure
your own real-world accuracy.

Fixtures, source attribution, selected filenames, reference texts, and SHA-256
checksums are cached in `~/.cache/dictation-benchmark/fixtures/`. Every run writes
a separate private folder under `~/.cache/dictation-benchmark/reports/` containing
`report.md`, detailed `report.json`, WAVs, references, transcripts, and diagnostic
logs. Subsequent runs reuse the exact fixture and verify its checksums. Use
`--cache /another/path` before the subcommand to change the cache location, or
`--output /new/report/directory` to choose a report directory.

The report shows word error rate (WER): substitutions + deletions + insertions,
divided by reference word count. Lower is better; WER can exceed 100%. Scoring
ignores case and punctuation, preserves internal apostrophes and Danish letters,
and splits hyphenated words. Numeric spellings are not converted to spoken words,
so `20` and `twenty` count as different. Some errors can therefore reflect number
formatting rather than misheard speech. JSON additionally includes scores after
the notation dictionary and with case-sensitive spelling, plus edit counts.
Do not compare these scores directly to published scores with other normalization
rules or datasets. A 1% WER target is demanding and is not guaranteed by any model.

Each model runs twice by default. All inference timings, median, best, model-load
time, backend, and whole-process wall time are saved separately. Inference timing
excludes input conversion, loading, and pasting. The first inference can include
GPU initialization. This measures batch recognition of a complete file, **not**
the delay after stopping a live streaming dictation. Pause other heavy work for
fair timing comparisons. `--repeat 3` is available for more repetitions.

To compare another tool, import the saved WAV there and export its transcript.
Score it against the matching saved reference, optionally supplying a measured
processing time:

```sh
dictation-benchmark score /path/to/en_us.reference.txt friends-tool.txt \
  --label friends-tool --processing-seconds 3 --output friends-tool-score.json
```

Always use identical audio and references. If the other app only accepts a live
microphone, file import is not enough: it needs a virtual microphone route. That
route must feed the whole recording at normal speed, and its relevant latency is
the wait **after** the audio finishes. A three-second streaming completion delay
does not mean it processed five minutes of audio in three seconds.

For your friend's OpenAI setup, record the exact model ID alongside the result.
The current [official model documentation](https://developers.openai.com/api/docs/models/gpt-transcribe)
lists `gpt-transcribe` with duration-based pricing, which fits the description
of a model billed per minute, but does not confirm which model your friend uses.
They can transcribe the same exported WAV and return a text file to score with
`--label gpt-transcribe` (or their actual model ID). The local benchmark itself
requires no API key and makes no paid transcription requests.

The benchmark harness is Python using only the standard library plus FFmpeg;
recognition and the normal dictation controls remain the native Rust pipeline.
Scoring checks: `python3 -m unittest discover -s tests -p test_dictation_benchmark.py`.
