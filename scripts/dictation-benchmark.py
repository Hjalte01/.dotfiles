#!/usr/bin/env python3
"""Silent, local ASR benchmarks using fixed FLEURS test audio and references."""

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import tarfile
import tempfile
import time
import unicodedata
import urllib.request
import wave


REVISION = "3eb1f6e784e5439e3b42a0336b26efb5f423b1dd"
BASE = f"https://huggingface.co/datasets/google/fleurs/resolve/{REVISION}/data"
MODELS = {
    "live": "live-parakeet-ultra-Q8_0",
    "ultra": "parakeet-ultra-Q8_0",
    "old": "parakeet-tdt-0.6b-v3",
    "nemotron": "handy-computer/nemotron-3.5-asr-streaming-0.6b-gguf/"
    "nemotron-3.5-asr-streaming-0.6b-Q8_0.gguf",
}
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "dictation-benchmark"
DATA = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "com.pais.handy"


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def tokens(text, case_sensitive=False):
    text = unicodedata.normalize("NFKC", text).replace("’", "'").replace("‘", "'")
    if not case_sensitive:
        text = text.casefold()
    return re.findall(r"[^\W_]+(?:'[^\W_]+)*", text, re.UNICODE)


def score(reference, hypothesis, case_sensitive=False):
    """Minimum word edit distance with substitution/deletion/insertion counts."""
    ref, hyp = tokens(reference, case_sensitive), tokens(hypothesis, case_sensitive)
    if not ref:
        raise ValueError("The reference must contain at least one word")
    # Tuple: total edits, substitutions, deletions, insertions. Rolling rows
    # keep memory bounded even for a long conversation.
    prev = [(j, 0, 0, j) for j in range(len(hyp) + 1)]
    for i, word in enumerate(ref, 1):
        row = [(i, 0, i, 0)]
        for j, other in enumerate(hyp, 1):
            if word == other:
                row.append(prev[j - 1])
                continue
            e, s, d, ins = prev[j - 1]
            substitution = (e + 1, s + 1, d, ins)
            e, s, d, ins = prev[j]
            deletion = (e + 1, s, d + 1, ins)
            e, s, d, ins = row[-1]
            insertion = (e + 1, s, d, ins + 1)
            row.append(min((substitution, deletion, insertion), key=lambda item: item[0]))
        prev = row
    errors, substitutions, deletions, insertions = prev[-1]
    return dict(wer_percent=100 * errors / len(ref), reference_words=len(ref),
                hypothesis_words=len(hyp), substitutions=substitutions,
                deletions=deletions, insertions=insertions)


def convert(source, destination):
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(source),
                    "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(destination)],
                   check=True, capture_output=True)


def wav_seconds(path):
    with wave.open(str(path), "rb") as audio:
        return audio.getnframes() / audio.getframerate()


def prepare(language, seconds):
    """Select complete utterances in pinned archive order, without cherry picking."""
    folder = CACHE / "fixtures" / f"fleurs-{REVISION[:12]}-{language}-{seconds:g}s"
    manifest_path = folder / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        for name, expected in manifest["files_sha256"].items():
            if digest((folder / name).read_bytes()) != expected:
                raise ValueError(f"Fixture changed: {folder / name}; use a fresh --cache")
        print(f"Using cached {language}: {manifest['audio_seconds']:.2f}s", flush=True)
        return folder
    folder.mkdir(parents=True, exist_ok=True)
    meta_url, archive_url = f"{BASE}/{language}/test.tsv", f"{BASE}/{language}/audio/test.tar.gz"
    print(f"Downloading FLEURS {language} test references and ~{seconds:g}s audio…", flush=True)
    with urllib.request.urlopen(meta_url, timeout=60) as response:
        metadata = response.read()
    rows = {row[1]: row for row in csv.reader(io.StringIO(metadata.decode()), delimiter="\t")}
    entries, frames, reference = [], bytearray(), []
    # Stream only the beginning of the archive; never extract archive paths.
    with urllib.request.urlopen(archive_url, timeout=90) as response:
        with tarfile.open(fileobj=response, mode="r|gz") as archive:
            for member in archive:
                name = Path(member.name).name
                if not member.isfile() or name not in rows:
                    continue
                raw = archive.extractfile(member).read()
                row = rows[name]
                with tempfile.TemporaryDirectory(prefix="dictation-audio-") as scratch:
                    original, converted = Path(scratch) / "source.wav", Path(scratch) / "audio.wav"
                    original.write_bytes(raw)
                    convert(original, converted)
                    with wave.open(str(converted), "rb") as audio:
                        pcm = audio.readframes(audio.getnframes())
                frames.extend(pcm)
                reference.append(row[2])
                entries.append(dict(filename=name, id=row[0], sha256=digest(raw),
                                    audio_seconds=len(pcm) / 32000, reference=row[2]))
                if len(frames) / 32000 >= seconds:
                    break
    if len(frames) / 32000 < seconds:
        raise ValueError("Not enough audio in the source archive")
    with wave.open(str(folder / "audio.wav"), "wb") as audio:
        audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        audio.writeframes(frames)
    (folder / "reference.txt").write_text("\n".join(reference) + "\n")
    manifest = dict(dataset="google/fleurs", revision=REVISION, split="test", language=language,
                    license="CC-BY-4.0", attribution="Google FLEURS contributors",
                    metadata_url=meta_url, metadata_sha256=digest(metadata), audio_url=archive_url,
                    selection="Complete utterances in archive order until requested duration",
                    audio_seconds=len(frames) / 32000, clips=entries,
                    caveat="Concatenated read speech from multiple speakers, not a conversation",
                    files_sha256={name: digest((folder / name).read_bytes())
                                  for name in ["audio.wav", "reference.txt"]})
    save_json(manifest_path, manifest)
    return folder


def report(output, results):
    save_json(output / "report.json", results)
    lines = ["# Dictation benchmark", "", "| Fixture | Model | Audio (s) | Inference median (s) | Load (s) | WER |",
             "| --- | --- | ---: | ---: | ---: | ---: |"]
    for row in results:
        lines.append(f"| {row['fixture']} | {row['label']} | {row['audio_seconds']:.2f} | "
                     f"{row['inference_median_seconds']:.3f} | {row['load_seconds']:.3f} | "
                     f"{row['score']['wer_percent']:.2f}% |")
    lines += ["", "WER = (substitutions + deletions + insertions) / reference words. Lower is better.",
              "Scoring ignores case and punctuation; internal apostrophes are preserved. Numbers are not verbalized.",
              "Case-sensitive WER, dictionary-corrected WER, all timings and transcripts are in report.json.",
              "", "Times measure accelerated file processing, excluding loading, resampling and pasting.",
              "The live model tests its complete-recording accuracy pass. Recurring previews are omitted.",
              "Use dictation-live replay to measure actual live preview and completion latency.",
              "The first inference may include GPU initialization; all repeats are retained, with median and best.",
              "This does not measure streaming latency after stopping speech or microphone/clipboard behavior.",
              "FLEURS fixtures are concatenated test-set read speech, not spontaneous conversations.",
              "Models may have seen public benchmarks; scores do not establish accuracy on unseen conversations.", ""]
    (output / "report.md").write_text("\n".join(lines))


def benchmark(fixtures, args):
    output = args.output or CACHE / "reports" / time.strftime("%Y%m%d-%H%M%S")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    results = []
    handy = os.environ.get("DICTATION_BENCHMARK_HANDY", "handy")
    model_dir = DATA / "models"
    if not model_dir.is_dir():
        raise ValueError(f"No installed Handy models at {model_dir}")
    # Headless Handy sees isolated settings and existing model symlinks only.
    # It never opens a microphone, types, or changes the live model/settings.
    with tempfile.TemporaryDirectory(prefix="dictation-benchmark-") as scratch:
        isolated = Path(scratch) / "data" / "com.pais.handy"
        isolated.mkdir(parents=True)
        (isolated / "models").symlink_to(model_dir, target_is_directory=True)
        save_json(isolated / "settings_store.json", {"settings": {
            "selected_language": "auto", "model_unload_timeout": "never",
            "post_process_enabled": False, "start_hidden": True}})
        env = dict(os.environ, XDG_DATA_HOME=str(Path(scratch) / "data"),
                   XDG_CONFIG_HOME=str(Path(scratch) / "config"))
        for fixture, audio, reference_path in fixtures:
            reference = reference_path.read_text()
            score(reference, "")  # Validate before running potentially long inference.
            if args.command == "suite":
                shutil.copyfile(audio.parent / "manifest.json", output / f"{fixture}.manifest.json")
            converted = output / f"{fixture}.wav"
            convert(audio, converted)
            (output / f"{fixture}.reference.txt").write_text(reference)
            for label in args.models:
                model_id = MODELS.get(label, label)
                print(f"Transcribing {fixture} with {label} ({wav_seconds(converted):.2f}s, "
                      f"{args.repeat} runs)…", flush=True)
                safe_label = re.sub(r"[^\w.-]", "_", label)
                prefix = output / f"{fixture}.{safe_label}"
                started = time.perf_counter()
                invocation = (["dictation-live", "transcribe-file", str(converted), "--repeat", str(args.repeat)]
                              if label == "live" else
                              [handy, "--transcribe-file", str(converted), "--model", model_id,
                               "--repeat", str(args.repeat), "--json"])
                try:
                    process = subprocess.run(invocation,
                                             env=env, capture_output=True, text=True, timeout=args.timeout)
                except subprocess.TimeoutExpired as error:
                    Path(f"{prefix}.stderr.log").write_bytes(error.stderr or b"")
                    raise RuntimeError(f"{label} timed out after {args.timeout:g}s; "
                                       f"see {prefix}.stderr.log") from error
                elapsed = time.perf_counter() - started
                Path(f"{prefix}.stderr.log").write_text(process.stderr)
                if process.returncode:
                    raise RuntimeError(f"{label} failed; see {prefix}.stderr.log")
                raw = json.loads(process.stdout)
                hypothesis = raw["text"]
                corrected = subprocess.run(["dictation", "normalize"], input=hypothesis,
                                           capture_output=True, text=True, check=True).stdout
                Path(f"{prefix}.txt").write_text(hypothesis + "\n")
                Path(f"{prefix}.corrected.txt").write_text(corrected)
                timings = [value / 1000 for value in raw["transcribe_ms"]]
                row = dict(fixture=fixture, label=label, model=model_id, backend=raw["bound_backend"],
                           audio_seconds=raw["audio_secs"], load_seconds=raw["load_ms"] / 1000,
                           inference_seconds=timings, inference_median_seconds=statistics.median(timings),
                           inference_best_seconds=min(timings), process_wall_seconds=elapsed,
                           transcript_run=args.repeat,
                           score=score(reference, hypothesis), corrected_score=score(reference, corrected),
                           case_sensitive_score=score(reference, corrected, case_sensitive=True),
                           transcript=hypothesis, corrected_transcript=corrected,
                           audio_sha256=digest(converted.read_bytes()),
                           reference_sha256=digest(reference_path.read_bytes()),
                           handy_binary=handy)
                row["mode"] = raw.get("mode", "full_file_batch")
                row["recognizer_binary"] = shutil.which("dictation-live") if label == "live" else handy
                results.append(row)
                report(output, results)
                print(f"  WER {row['score']['wer_percent']:.2f}% | "
                      f"inference {statistics.median(timings):.3f}s median | load {row['load_seconds']:.3f}s",
                      flush=True)
    print(f"Report: {output / 'report.md'}", flush=True)


def positive(value):
    number = float(value)
    if not 0 < number <= 86400:
        raise argparse.ArgumentTypeError("must be greater than zero and at most 86400")
    return number


def main():
    global CACHE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=CACHE)
    commands = parser.add_subparsers(dest="command", required=True)
    suite = commands.add_parser("suite", help="download fixed English/Danish test audio and benchmark silently")
    suite.add_argument("--language", choices=["both", "en", "da"], default="both")
    suite.add_argument("--seconds", type=positive, default=300)
    run = commands.add_parser("run", help="benchmark your own audio against a checked reference transcript")
    run.add_argument("audio", type=Path)
    run.add_argument("reference", type=Path)
    for command in [suite, run]:
        command.add_argument("--models", nargs="+", default=["old", "ultra"],
                             help="live, old, ultra, nemotron, or installed Handy model IDs")
        command.add_argument("--repeat", type=int, choices=range(1, 11), default=2)
        command.add_argument("--timeout", type=positive, default=900)
        command.add_argument("--output", type=Path, help="new directory for reports, transcripts and WAVs")
    scoring = commands.add_parser("score", help="score text exported from any other dictation tool")
    scoring.add_argument("reference", type=Path)
    scoring.add_argument("transcript", type=Path)
    scoring.add_argument("--label", default="external")
    scoring.add_argument("--processing-seconds", type=positive)
    scoring.add_argument("--case-sensitive", action="store_true")
    scoring.add_argument("--output", type=Path, help="optional JSON result file")
    args = parser.parse_args()
    CACHE = args.cache.resolve()
    os.umask(0o077)
    if args.command != "score":
        required = [os.environ.get("DICTATION_BENCHMARK_HANDY", "handy"), "ffmpeg", "dictation"]
        if "live" in args.models:
            required.append("dictation-live")
        for executable in required:
            if not shutil.which(executable):
                raise ValueError(f"Required executable missing: {executable}")
    if args.command == "score":
        result = dict(label=args.label, score=score(args.reference.read_text(), args.transcript.read_text(),
                                                  args.case_sensitive),
                      processing_seconds=args.processing_seconds,
                      reference_sha256=digest(args.reference.read_bytes()),
                      transcript_sha256=digest(args.transcript.read_bytes()))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.output:
            save_json(args.output, result)
    elif args.command == "suite":
        languages = ["en_us", "da_dk"] if args.language == "both" else [dict(en="en_us", da="da_dk")[args.language]]
        fixtures = []
        for language in languages:
            folder = prepare(language, args.seconds)
            fixtures.append((language, folder / "audio.wav", folder / "reference.txt"))
        benchmark(fixtures, args)
    else:
        benchmark([("custom", args.audio.resolve(), args.reference.resolve())], args)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError, tarfile.TarError) as error:
        sys.exit(f"dictation-benchmark: {error}")
