"""Image history tests use synthetic PNGs and never access the real clipboard."""

import importlib.util
from io import BytesIO
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "imagepick_core.py"
SPEC = importlib.util.spec_from_file_location("imagepick_core", MODULE_PATH)
core = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = core
SPEC.loader.exec_module(core)


def png_bytes(color="red"):
    data = BytesIO()
    Image.new("RGB", (12, 8), color).save(data, format="PNG")
    return data.getvalue()


def completed(stdout=b"", returncode=0, stderr=b""):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


class HistoryTests(unittest.TestCase):
    def test_screenshots_and_edits_share_order_and_limit_without_deeper_recursion(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            older, newest = folder / "old.png", folder / "new.JPG"
            older.write_bytes(png_bytes())
            newest.write_bytes(png_bytes())
            os.utime(older, (1, 1))
            os.utime(newest, (2, 2))
            (folder / "notes.txt").write_text("ignore")
            (folder / "Edited").mkdir()
            edited = folder / "Edited" / "edit.png"
            edited.write_bytes(png_bytes())
            os.utime(edited, (3, 3))
            (folder / "Edited" / "Nested").mkdir()
            (folder / "Edited" / "Nested" / "deep.png").write_bytes(png_bytes())
            (folder / "Other").mkdir()
            (folder / "Other" / "unrelated.png").write_bytes(png_bytes())
            entries = core.discover_screenshots(folder)
            self.assertEqual([entry.path for entry in entries], [edited, newest, older])
            self.assertEqual(entries[0].label, "Edited/edit.png")
            self.assertEqual(entries[0].key, f"screenshot:{edited.absolute()}")
            self.assertEqual([entry.path for entry in core.discover_screenshots(folder, limit=2)], [edited, newest])

    def test_missing_screenshot_folder_is_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(core.discover_screenshots(Path(directory) / "missing"), [])

    @patch.object(core.subprocess, "run")
    def test_clipboard_only_lists_image_descriptors_without_decoding_text(self, run):
        run.return_value = completed(
            b"12\tprivate copied text\n9\t[[ binary data 123 B png 12x8 ]]\n"
            b"13\t[[ binary data 4 KiB jpeg 300x200 ]]\n11\t[[ binary data 2 KiB pdf ]]\n"
        )
        entries = core.discover_clipboard()
        self.assertEqual([entry.key for entry in entries], ["clipboard:13", "clipboard:9"])
        self.assertTrue(all("private copied text" not in entry.label for entry in entries))
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], ["cliphist", "list"])


class MaterializationTests(unittest.TestCase):
    @patch.object(core.subprocess, "run")
    def test_decode_is_lazy_private_and_cached(self, run):
        run.return_value = completed(png_bytes())
        record = "9\t[[ binary data 123 B png 12x8 ]]"
        entry = core.Entry("clipboard:9", "Image", "clipboard", clipboard_record=record)
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "cache"
            path = core.materialize(entry, cache)
            with Image.open(path) as image:
                self.assertEqual(image.size, (12, 8))
            self.assertEqual(cache.stat().st_mode & 0o777, 0o700)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(core.materialize(entry, cache), path)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.kwargs["input"], record.encode())

    def test_jpeg_normalizes_to_png_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "photo.jpg"
            Image.new("RGB", (12, 8), "blue").save(source)
            original = source.read_bytes()
            entry = core.Entry("screenshot:test", "photo", "screenshots", path=source)
            result = core.materialize(entry, folder / "cache")
            with Image.open(result) as image:
                self.assertEqual(image.format, "PNG")
            self.assertEqual(source.read_bytes(), original)

    @patch.object(core.subprocess, "run")
    def test_invalid_clipboard_payload_reports_error(self, run):
        run.return_value = completed(b"not an image")
        entry = core.Entry("clipboard:9", "Image", "clipboard", clipboard_record="9\timage")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(core.ImagepickError):
                core.materialize(entry, directory)


class DesktopTests(unittest.TestCase):
    @patch.object(core.subprocess, "run")
    def test_copy_uses_png_mime_and_pixels(self, run):
        run.return_value = completed()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.png"
            path.write_bytes(png_bytes())
            core.copy_image(path)
            self.assertEqual(run.call_args.args[0], ["wl-copy", "--type", "image/png"])
            self.assertTrue(run.call_args.kwargs["input"].startswith(b"\x89PNG"))

    @patch.object(core.subprocess, "run")
    def test_editor_cancel_leaves_original_and_no_empty_edit(self, run):
        run.return_value = completed()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "source.png"
            source.write_bytes(png_bytes())
            original = source.read_bytes()
            self.assertIsNone(core.edit_image(source, "crop", folder))
            self.assertEqual(list((folder / "Edited").iterdir()), [])
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(run.call_count, 1)

    @patch.object(core.subprocess, "run")
    def test_editor_saves_new_file_and_copies_after_save(self, run):
        def run_fake(command, **kwargs):
            if command[0] == "satty":
                config = Path(command[command.index("--config") + 1])
                self.assertIn("early-exit = false", config.read_text())
                self.assertNotIn("--early-exit", command)
                output = Path(command[command.index("--output-filename") + 1])
                self.assertEqual(output.stat().st_mode & 0o777, 0o600)
                output.write_bytes(png_bytes("blue"))
                self.assertEqual(command[command.index("--actions-on-enter") + 1], "save-to-file,save-to-clipboard,exit")
            return completed()
        run.side_effect = run_fake
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "source.png"
            source.write_bytes(png_bytes())
            original = source.read_bytes()
            result = core.edit_image(source, "arrow", folder)
            self.assertEqual(result.parent, folder / "Edited")
            self.assertNotEqual(result, source)
            self.assertEqual(result.stat().st_mode & 0o777, 0o600)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(run.call_args.args[0], ["wl-copy", "--type", "image/png"])

    @patch.object(core.subprocess, "run")
    def test_clipboard_failure_preserves_saved_edit(self, run):
        def run_fake(command, **kwargs):
            if command[0] == "satty":
                Path(command[command.index("--output-filename") + 1]).write_bytes(png_bytes("blue"))
                return completed()
            return completed(returncode=1, stderr=b"No Wayland display")
        run.side_effect = run_fake
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "source.png"
            source.write_bytes(png_bytes())
            with self.assertRaisesRegex(core.ImagepickError, "No Wayland display") as raised:
                core.edit_image(source, "brush", folder)
            saved = list((folder / "Edited").glob("*.png"))
            self.assertEqual(len(saved), 1)
            self.assertIn(str(saved[0]), str(raised.exception))
            self.assertIn("Saved image preserved", str(raised.exception))
            self.assertIn("Clipboard copy failed", str(raised.exception))

    @patch.object(core.subprocess, "run")
    def test_missing_command_and_timeout_have_useful_errors(self, run):
        run.side_effect = FileNotFoundError()
        with self.assertRaisesRegex(core.ImagepickError, "unavailable"):
            core.discover_clipboard()
        run.side_effect = subprocess.TimeoutExpired("cliphist", 15)
        with self.assertRaisesRegex(core.ImagepickError, "15 seconds"):
            core.discover_clipboard()


if __name__ == "__main__":
    unittest.main()
