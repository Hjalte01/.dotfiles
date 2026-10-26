"""Headless imagepick interactions with synthetic images and no desktop writes."""

import asyncio
from contextlib import ExitStack
import importlib
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from PIL import Image
from textual.widgets import ListView, Static


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import imagepick


class ImagePickerUI(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = ExitStack()
        # Other source-file tests may replace sys.modules during collection.
        # Resolve the same module create_app imports before applying the guard.
        self.core = importlib.import_module("imagepick_core")
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.screenshot_dir = self.root / "Screenshots"
        self.screenshot_dir.mkdir()
        self.cache = self.root / "cache"
        self.screenshots = [self.entry("new.png", "screenshots", "red"),
                            self.entry("older.png", "screenshots", "blue")]
        self.clipboard = [self.entry("copied.png", "clipboard", "green")]
        self.discover_screenshots = self.stack.enter_context(
            patch.object(self.core, "discover_screenshots", return_value=self.screenshots))
        self.discover_clipboard = self.stack.enter_context(
            patch.object(self.core, "discover_clipboard", return_value=self.clipboard))
        self.copy = self.stack.enter_context(patch.object(self.core, "copy_image"))
        self.edit = self.stack.enter_context(patch.object(self.core, "edit_image", return_value=None))
        # A hard guard against accidentally touching the real clipboard/editor.
        self.process = self.stack.enter_context(
            patch.object(self.core.subprocess, "run", side_effect=AssertionError("Unexpected desktop command")))

    def tearDown(self):
        self.stack.close()

    def entry(self, name, source, color):
        path = self.screenshot_dir / name
        Image.new("RGB", (32, 18), color).save(path)
        return self.core.Entry(f"{source}:{name}", name, source, path=path)

    def app(self, **kwargs):
        return imagepick.create_app(self.screenshot_dir, self.cache, renderer="halfcell", **kwargs)

    async def settle(self, app, pilot):
        # History workers may enqueue preview workers after their own completion.
        for _ in range(2):
            await app.workers.wait_for_complete()
            await pilot.pause()

    def content(self, app, selector):
        return str(app.query_one(selector, Static).render())

    async def test_source_switch_loads_preview_and_remembers_selection(self):
        app = self.app()
        async with app.run_test(size=(110, 34)) as pilot:
            await self.settle(app, pilot)
            self.assertEqual(app.selected, self.screenshots[0])
            self.assertTrue(app.selected_path.is_file())
            self.assertTrue(app.query_one("#preview").display)
            self.assertFalse(app.query_one("#empty").display)
            self.assertIn("32 × 18", self.content(app, "#info"))
            await pilot.press("j")
            await self.settle(app, pilot)
            self.assertEqual(app.selected, self.screenshots[1])
            await pilot.press("tab")
            await self.settle(app, pilot)
            self.assertEqual(app.source, "clipboard")
            self.assertEqual(app.selected, self.clipboard[0])
            self.assertIn("copied.png", self.content(app, "#info"))
            await pilot.press("tab")
            await self.settle(app, pilot)
            self.assertEqual(app.selected, self.screenshots[1])
            self.assertEqual(len(app.query_one("#history", ListView).children), 2)
            self.copy.assert_not_called()
            self.edit.assert_not_called()

    async def test_browsing_wraps_and_copy_uses_current_image(self):
        app = self.app()
        async with app.run_test(size=(80, 24)) as pilot:
            await self.settle(app, pilot)
            await pilot.press("k")
            await self.settle(app, pilot)
            self.assertEqual(app.selected, self.screenshots[-1])
            await pilot.press("down")
            await self.settle(app, pilot)
            self.assertEqual(app.selected, self.screenshots[0])
            await pilot.press("j")
            await self.settle(app, pilot)
            copied_path = app.selected_path
            await pilot.press("y")
            await self.settle(app, pilot)
            self.copy.assert_called_once_with(copied_path)
            self.assertIn("Image copied", self.content(app, "#status"))
            self.assertTrue(app.has_class("narrow"))

    async def test_edit_from_clipboard_selects_saved_output_in_screenshots(self):
        edited = self.screenshot_dir / "Edited" / "saved-arrow.png"
        edited.parent.mkdir()
        Image.new("RGB", (20, 10), "yellow").save(edited)
        self.edit.return_value = edited
        saved_entry = self.core.Entry(f"screenshot:{edited.absolute()}", edited.name,
                                     "screenshots", path=edited)
        self.discover_screenshots.return_value = [saved_entry, *self.screenshots]
        app = self.app(source="clipboard")
        async with app.run_test(size=(110, 34)) as pilot:
            await self.settle(app, pilot)
            original_preview = app.selected_path
            await pilot.press("a")
            await self.settle(app, pilot)
            self.edit.assert_called_once_with(original_preview, "arrow", self.screenshot_dir)
            self.assertEqual(app.source, "screenshots")
            self.assertEqual(app.selected.path, edited)
            self.assertEqual(app.remembered["screenshots"], app.selected.key)
            self.assertEqual(len(app.edited), 1)
            self.assertEqual(len(app.query_one("#history", ListView).children), 3)
            self.assertTrue(app.selected_path.is_file())
            self.assertIn("20 × 10", self.content(app, "#info"))
            self.assertIn(str(edited), self.content(app, "#status"))
            self.copy.assert_not_called()  # The backend editor owns its save/copy action.

    async def test_cancelled_crop_keeps_original_selection_and_preview(self):
        app = self.app()
        async with app.run_test(size=(110, 34)) as pilot:
            await self.settle(app, pilot)
            selected, preview = app.selected, app.selected_path
            original = selected.path.read_bytes()
            await pilot.press("c")
            await self.settle(app, pilot)
            self.edit.assert_called_once_with(preview, "crop", self.screenshot_dir)
            self.assertEqual(app.selected, selected)
            self.assertEqual(app.selected_path, preview)
            self.assertEqual(selected.path.read_bytes(), original)
            self.assertFalse(app.edited)
            self.assertIn("No new image saved", self.content(app, "#status"))

    async def test_unavailable_source_can_switch_to_working_source(self):
        self.discover_clipboard.side_effect = self.core.ImagepickError("Clipboard history is unavailable")
        app = self.app(source="clipboard")
        async with app.run_test(size=(110, 34)) as pilot:
            await self.settle(app, pilot)
            self.assertIsNone(app.selected)
            self.assertIsNone(app.selected_path)
            self.assertFalse(app.query_one("#preview").display)
            self.assertIn("Source unavailable", self.content(app, "#count"))
            self.assertIn("Clipboard history is unavailable", self.content(app, "#empty"))
            await pilot.press("y")
            await self.settle(app, pilot)
            self.copy.assert_not_called()
            self.assertIn("Select an image first", self.content(app, "#status"))
            await pilot.press("tab")
            await self.settle(app, pilot)
            self.assertEqual(app.selected, self.screenshots[0])
            self.assertTrue(app.query_one("#preview").display)

    async def test_invalid_image_shows_error_and_browsing_recovers(self):
        self.screenshots[0].path.write_bytes(b"invalid image bytes")
        app = self.app()
        async with app.run_test(size=(110, 34)) as pilot:
            await self.settle(app, pilot)
            self.assertEqual(app.selected, self.screenshots[0])
            self.assertIsNone(app.selected_path)
            self.assertFalse(app.query_one("#preview").display)
            self.assertIn("Cannot read image", self.content(app, "#empty"))
            await pilot.press("y")
            await self.settle(app, pilot)
            self.copy.assert_not_called()
            self.assertIn("Cannot read image", self.content(app, "#status"))
            await pilot.press("j")
            await self.settle(app, pilot)
            self.assertEqual(app.selected, self.screenshots[1])
            self.assertTrue(app.query_one("#preview").display)

    async def test_empty_source_has_help_and_no_operations(self):
        self.discover_screenshots.return_value = []
        app = self.app()
        async with app.run_test(size=(110, 34)) as pilot:
            await self.settle(app, pilot)
            self.assertIsNone(app.selected)
            self.assertIn("No screenshots yet", self.content(app, "#empty"))
            await pilot.press("j", "c")
            await self.settle(app, pilot)
            self.edit.assert_not_called()
            self.assertIn("Select an image first", self.content(app, "#status"))

    async def test_slow_old_source_does_not_replace_new_source(self):
        entered, release = threading.Event(), threading.Event()

        def slow_discovery(*_args):
            entered.set()
            if not release.wait(timeout=5):
                raise AssertionError("Test did not release screenshot discovery")
            return self.screenshots

        self.discover_screenshots.side_effect = slow_discovery
        app = self.app()
        try:
            async with app.run_test(size=(110, 34)) as pilot:
                self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                await pilot.press("tab")
                await self.settle(app, pilot)
                self.assertEqual(app.source, "clipboard")
                self.assertEqual(app.selected, self.clipboard[0])
                release.set()
                await self.settle(app, pilot)
                self.assertEqual(app.source, "clipboard")
                self.assertEqual(app.selected, self.clipboard[0])
                self.assertEqual(len(app.query_one("#history", ListView).children), 1)
        finally:
            release.set()


if __name__ == "__main__":
    unittest.main()
