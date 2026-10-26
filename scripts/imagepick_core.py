"""Local image history and editing operations used by imagepick.

Discovery never decodes clipboard text. Selected image data lives only in the
caller's private session cache; edits are saved separately from their originals.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
from io import BytesIO
import os
from pathlib import Path
import re
import subprocess
import tempfile
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError


IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".avif"})
CLIPBOARD_IMAGE = re.compile(
    r"^\[\[ binary data .+\b(?:png|jpe?g|webp|gif|bmp|tiff?|avif)\b(?: \d+x\d+)? \]\]$",
    re.IGNORECASE,
)


class ImagepickError(RuntimeError):
    """An image source or desktop operation could not be completed."""


@dataclass(frozen=True)
class Entry:
    key: str
    label: str
    source: str
    path: Path | None = None
    clipboard_record: str | None = None


def screenshot_directory() -> Path:
    """Match the existing PrtSc screenshot bindings."""
    return Path.home() / "Pictures" / "Screenshots"


def _label(value: str) -> str:
    return "".join(character if character.isprintable() else " " for character in value)


def _run(command: list[str], *, data: bytes | None = None, timeout: int = 15) -> bytes:
    try:
        result = subprocess.run(command, input=data, capture_output=True, timeout=timeout, check=False)
    except FileNotFoundError as error:
        raise ImagepickError(f"{command[0]} is unavailable. Activate the desktop configuration with nxb.") from error
    except subprocess.TimeoutExpired as error:
        raise ImagepickError(f"{command[0]} did not finish within {timeout} seconds.") from error
    except OSError as error:
        raise ImagepickError(f"Cannot start {command[0]}: {error}") from error
    if result.returncode:
        detail = _label(result.stderr.decode("utf-8", errors="replace").strip())[:240]
        raise ImagepickError(f"{command[0]} failed" + (f": {detail}" if detail else f" (exit {result.returncode})."))
    return result.stdout


def discover_screenshots(screenshot_dir: Path | str, limit: int = 200) -> list[Entry]:
    """Merge screenshots and direct Edited/ children newest first."""
    directory = Path(screenshot_dir).expanduser()
    try:
        children = list(directory.iterdir())
    except FileNotFoundError:
        return []
    except OSError as error:
        raise ImagepickError(f"Cannot read screenshot folder: {error}") from error
    try:
        children.extend((directory / "Edited").iterdir())
    except (FileNotFoundError, NotADirectoryError):
        pass
    except OSError as error:
        raise ImagepickError(f"Cannot read edited image folder: {error}") from error
    files = []
    for path in children:
        try:
            if path.suffix.lower() in IMAGE_EXTENSIONS and path.is_file():
                files.append((path.stat().st_mtime_ns, path))
        except OSError:
            continue
    files.sort(key=lambda item: (item[0], str(item[1])), reverse=True)
    return [
        Entry(key=f"screenshot:{path.absolute()}", label=_label(path.relative_to(directory).as_posix()),
              source="screenshots", path=path)
        for _, path in files[:max(0, limit)]
    ]


def discover_clipboard(limit: int = 200) -> list[Entry]:
    """Read image descriptors only; clipboard payloads are decoded on selection."""
    listing = _run(["cliphist", "list"]).decode("utf-8", errors="replace")
    entries = []
    for record in listing.splitlines():
        identifier, separator, descriptor = record.partition("\t")
        if not separator or not identifier.isdecimal() or not CLIPBOARD_IMAGE.fullmatch(descriptor):
            continue
        entries.append(Entry(
            key=f"clipboard:{identifier}",
            label=f"Copy {identifier} · {_label(descriptor[3:-3])}",
            source="clipboard",
            clipboard_record=record,
        ))
    # cliphist orders by decreasing integer IDs, independent of text previews.
    entries.sort(key=lambda entry: int(entry.key.partition(":")[2]), reverse=True)
    return entries[:max(0, limit)]


def _png_bytes(source: Path | BytesIO) -> bytes:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(source) as original:
                original.seek(0)
                oriented = ImageOps.exif_transpose(original)
                image = oriented.convert("RGBA" if "A" in oriented.getbands() or "transparency" in oriented.info else "RGB")
                output = BytesIO()
                image.save(output, format="PNG")
                return output.getvalue()
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ImagepickError(f"Cannot read image: {error}") from error


def materialize(entry: Entry, cache_dir: Path | str) -> Path:
    """Return a PNG in a private session cache, never altering the input image."""
    directory = Path(cache_dir)
    try:
        directory.mkdir(parents=True, mode=0o700, exist_ok=True)
        directory.chmod(0o700)
        target = directory / (hashlib.sha256(entry.key.encode()).hexdigest() + ".png")
        if target.exists() and (
            entry.path is None or entry.path.stat().st_mtime_ns <= target.stat().st_mtime_ns
        ):
            return target
        if entry.path is not None:
            data = _png_bytes(entry.path)
        elif entry.clipboard_record is not None:
            payload = _run(["cliphist", "decode"], data=entry.clipboard_record.encode("utf-8"))
            if not payload:
                raise ImagepickError("This clipboard image is no longer available. Refresh the history.")
            data = _png_bytes(BytesIO(payload))
        else:
            raise ImagepickError("This history entry has no image source.")
        descriptor, temporary = tempfile.mkstemp(prefix=".imagepick-", suffix=".png", dir=directory)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(data)
            Path(temporary).replace(target)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return target
    except OSError as error:
        raise ImagepickError(f"Cannot cache image: {error}") from error


def copy_image(path: Path | str) -> None:
    """Copy the selected image pixels with an explicit MIME type."""
    _run(["wl-copy", "--type", "image/png"], data=_png_bytes(Path(path)))


def edit_image(path: Path | str, tool: str, screenshot_dir: Path | str) -> Path | None:
    """Open Satty and return a separate saved PNG, or None after cancellation.

    A private config prevents a user's early-exit preference from skipping the
    remaining Enter actions. Satty 0.20.1 stops processing as soon as an action
    sees early-exit=true, so this must be false for save/copy/exit sequencing.
    """
    if tool not in {"crop", "arrow", "brush", "pointer"}:
        raise ImagepickError(f"Unknown editing tool: {tool}")
    image_path = Path(path)
    # Validate before creating an output placeholder or opening an editor.
    _png_bytes(image_path)
    edited_dir = Path(screenshot_dir).expanduser() / "Edited"
    output: Path | None = None
    try:
        edited_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        descriptor, filename = tempfile.mkstemp(prefix=f"imagepick-{timestamp}-", suffix=".png", dir=edited_dir)
        os.close(descriptor)
        output = Path(filename)
        with tempfile.TemporaryDirectory(prefix="imagepick-editor-") as config_dir:
            config = Path(config_dir) / "config.toml"
            config.write_text('[general]\nearly-exit = false\nearly-exit-save-as = false\n')
            _run([
                "satty", "--config", str(config), "--filename", str(image_path),
                "--output-filename", str(output).replace("%", "%%"),
                "--initial-tool", tool, "--copy-command", "wl-copy --type image/png",
                "--actions-on-enter", "save-to-file,save-to-clipboard,exit",
                "--actions-on-escape", "exit",
                "--fullscreen", "current-screen",
            ], timeout=3600)
        if not output.exists() or not output.stat().st_size:
            output.unlink(missing_ok=True)
            return None
        # Validate the saved image and also copy after Ctrl+S followed by Escape.
        # Unlike Satty's notification-only failures, this reports clipboard errors.
        output.chmod(0o600)
        try:
            copy_image(output)
        except ImagepickError as error:
            raise ImagepickError(f"Saved image preserved at {output}. Clipboard copy failed: {error}") from error
        return output
    except OSError as error:
        raise ImagepickError(f"Cannot save edited image: {error}") from error
    finally:
        # Retain successfully saved work even when clipboard copying fails.
        if output is not None and output.exists() and not output.stat().st_size:
            output.unlink(missing_ok=True)
