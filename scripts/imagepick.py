#!/usr/bin/env python3
"""Browse local image history with terminal previews and quick Satty editing."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import sys
import tempfile


def create_app(screenshot_dir: Path, cache_dir: Path, *, source="screenshots", limit=200,
               renderer="auto"):
    # Probe graphics support before Textual starts its input reader. Keeping
    # imports here also lets --help work without querying the terminal.
    from PIL import Image as PILImage
    from textual import on, work
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Container, Horizontal, Vertical
    from textual.widgets import Button, Footer, Header, Label, ListItem, ListView, Static
    from textual_image.widget import HalfcellImage, Image, TGPImage

    from dotfiles_theme import install as install_theme
    import imagepick_core as core

    image_class = {"auto": Image, "tgp": TGPImage, "halfcell": HalfcellImage}[renderer]

    class ImageItem(ListItem):
        def __init__(self, entry):
            super().__init__(Label(entry.label, markup=False))
            self.entry = entry

    class ImagePicker(App):
        TITLE = "Recent images"
        CSS = """
        Screen { background: $background; }
        #sources { height: 3; padding: 0 1; background: $surface; }
        #sources Button { margin-right: 1; min-width: 18; }
        #body { height: 1fr; }
        #sidebar { width: 32%; min-width: 25; max-width: 48; border-right: solid $primary; }
        #count { height: 2; padding: 0 1; color: $text-muted; }
        #history { height: 1fr; }
        #history ListItem { height: auto; min-height: 2; padding: 0 1; }
        #history Label { width: 1fr; }
        #detail { padding: 0 1; }
        #info { height: 2; color: $text-muted; }
        #image-area { height: 1fr; align: center middle; overflow: hidden; }
        #preview { width: auto; height: auto; max-width: 100%; max-height: 100%; }
        #empty { width: 100%; height: auto; text-align: center; color: $text-muted; }
        #actions { height: 3; align-horizontal: center; }
        #actions Button { min-width: 10; margin: 0 1; }
        #status { height: 2; padding: 0 1; color: $text; background: $surface; }
        .narrow #sidebar { width: 34%; min-width: 19; }
        .narrow #actions Button { min-width: 7; margin: 0; }
        """
        BINDINGS = [
            Binding("tab,shift+tab", "switch_source", "Switch source", priority=True),
            Binding("j,down", "next_image", "Next", show=False, priority=True),
            Binding("k,up", "previous_image", "Previous", show=False, priority=True),
            Binding("c", "edit('crop')", "Crop"),
            Binding("a,enter", "edit('arrow')", "Arrow", priority=True),
            Binding("d", "edit('brush')", "Draw"),
            Binding("y", "copy_image", "Copy"),
            Binding("r", "refresh_history", "Refresh"),
            Binding("q,escape,ctrl+c", "close_picker", "Quit", priority=True),
        ]

        def __init__(self):
            super().__init__()
            self.source = source
            self.selected = None
            self.selected_path = None
            self.remembered = {}
            self.busy = False
            self.edited = {}  # Keep saved edits available for another crop/copy.
            self.generation = 0

        def compose(self) -> ComposeResult:
            yield Header()
            with Horizontal(id="sources"):
                yield Button("Screenshots", id="screenshots")
                yield Button("Copied images", id="clipboard")
            with Horizontal(id="body"):
                with Vertical(id="sidebar"):
                    yield Static("Loading images…", id="count")
                    yield ListView(id="history")
                with Vertical(id="detail"):
                    yield Static("", id="info", markup=False)
                    with Container(id="image-area"):
                        yield image_class(id="preview")
                        yield Static("Loading images…", id="empty", markup=False)
                    with Horizontal(id="actions"):
                        yield Button("Crop [c]", id="crop")
                        yield Button("Arrow [a]", id="arrow")
                        yield Button("Draw [d]", id="brush")
                        yield Button("Copy [y]", id="copy")
            yield Static("↑/↓ or j/k browse · Tab changes source · Enter edits", id="status", markup=False)
            yield Footer()

        def on_mount(self):
            install_theme(self)
            self.query_one("#preview").display = False
            self.load_history()

        def on_resize(self, event):
            self.set_class(event.size.width < 90, "narrow")

        def status(self, message):
            self.query_one("#status", Static).update(message)

        def clear_preview(self, message):
            self.selected_path = None
            preview = self.query_one("#preview")
            preview.image = None
            preview.display = False
            empty = self.query_one("#empty", Static)
            empty.update(message)
            empty.display = True
            self.query_one("#info", Static).update("")

        @work(exclusive=True, group="history")
        async def load_history(self):
            self.generation += 1
            generation = self.generation
            selected_source = self.source
            self.selected = None
            self.clear_preview("Loading images…")
            self.query_one("#count", Static).update("Loading images…")
            for name in ("screenshots", "clipboard"):
                self.query_one(f"#{name}", Button).variant = "primary" if name == selected_source else "default"
            history = self.query_one("#history", ListView)
            await history.clear()
            try:
                discover = (lambda: core.discover_screenshots(screenshot_dir, limit)) if selected_source == "screenshots" else (lambda: core.discover_clipboard(limit))
                entries = await asyncio.to_thread(discover)
            except core.ImagepickError as error:
                if generation == self.generation:
                    self.query_one("#count", Static).update("Source unavailable")
                    self.clear_preview(str(error))
                    self.status("Press r to retry, or Tab to change source.")
                return
            if generation != self.generation or selected_source != self.source:
                return
            # Prepend edits saved in this session so they can be edited again.
            edits = list(self.edited.values()) if selected_source == "screenshots" else []
            entries = edits + [entry for entry in entries if entry.key not in self.edited]
            count = len(entries)
            self.query_one("#count", Static).update(f"{count} image{'s' if count != 1 else ''} · newest first")
            if not entries:
                self.clear_preview("No copied images yet.\nCopy an image and press r." if selected_source == "clipboard" else f"No screenshots yet.\nTake one with PrtSc, then press r.\n{screenshot_dir}")
                return
            await history.extend(ImageItem(entry) for entry in entries)
            remembered = self.remembered.get(selected_source)
            history.index = next((i for i, entry in enumerate(entries) if entry.key == remembered), 0)
            history.focus()

        @on(ListView.Highlighted)
        def image_highlighted(self, event):
            if not isinstance(event.item, ImageItem):
                return
            self.selected = event.item.entry
            self.remembered[self.source] = self.selected.key
            self.clear_preview("Loading preview…")
            self.load_preview(self.selected)

        @work(exclusive=True, group="preview")
        async def load_preview(self, entry):
            try:
                path = await asyncio.to_thread(core.materialize, entry, cache_dir)
                with PILImage.open(path) as image:
                    width, height = image.size
                if self.selected != entry:
                    return
                self.selected_path = path
                preview = self.query_one("#preview")
                preview.image = path
                preview.display = True
                self.query_one("#empty").display = False
                label = str(entry.path) if entry.path else entry.label
                self.query_one("#info", Static).update(f"{width} × {height}   {label}")
            except (core.ImagepickError, OSError, ValueError) as error:
                if self.selected == entry:
                    self.clear_preview(str(error))

        def move(self, delta):
            history = self.query_one("#history", ListView)
            if history.children:
                history.index = ((history.index or 0) + delta) % len(history.children)
                history.focus()

        def action_next_image(self):
            self.move(1)

        def action_previous_image(self):
            self.move(-1)

        def action_switch_source(self):
            self.set_source("clipboard" if self.source == "screenshots" else "screenshots")

        def set_source(self, new_source):
            if not self.busy:
                self.source = new_source
                self.load_history()

        def action_refresh_history(self):
            if not self.busy:
                self.load_history()

        @on(Button.Pressed)
        def button_pressed(self, event):
            name = event.button.id
            if name in ("screenshots", "clipboard"):
                self.set_source(name)
            elif name == "copy":
                self.action_copy_image()
            elif name in ("crop", "arrow", "brush"):
                self.action_edit(name)

        def action_copy_image(self):
            self.operate("copy")

        def action_edit(self, tool):
            self.operate(tool)

        @work(group="operation")
        async def operate(self, action):
            if self.busy:
                return
            entry = self.selected
            if entry is None:
                self.status("Select an image first.")
                return
            self.busy = True
            try:
                path = await asyncio.to_thread(core.materialize, entry, cache_dir)
                if action == "copy":
                    await asyncio.to_thread(core.copy_image, path)
                    self.status("Image copied. Paste it with Ctrl+V.")
                else:
                    self.status("Satty is open · Enter saves and copies · Esc cancels")
                    saved = await asyncio.to_thread(core.edit_image, path, action, screenshot_dir)
                    if saved is None:
                        self.status("Editor closed. No new image saved.")
                    else:
                        edited = core.Entry(key=f"screenshot:{saved.absolute()}", label=saved.name,
                                            source="screenshots", path=saved)
                        self.edited = {edited.key: edited, **self.edited}
                        self.remembered["screenshots"] = edited.key
                        self.source = "screenshots"
                        self.load_history()
                        self.status(f"Saved and copied: {saved}")
            except core.ImagepickError as error:
                self.status(str(error))
            finally:
                self.busy = False

        def action_close_picker(self):
            if self.busy:
                self.status("Close Satty first, or wait for the clipboard operation to finish.")
            else:
                self.exit()

    return ImagePicker()


def positive_int(value):
    result = int(value)
    if result < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("screenshots", "clipboard"), default="screenshots")
    parser.add_argument("--limit", type=positive_int, default=200, help="maximum recent images per source (default: 200)")
    parser.add_argument("--screenshots-dir", type=Path, default=Path.home() / "Pictures" / "Screenshots")
    parser.add_argument("--renderer", choices=("auto", "tgp", "halfcell"), default="auto")
    args = parser.parse_args(argv)
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        parser.error("open imagepick in a terminal, or run imagepick-menu")
    # Kitty image placements encode their IDs in RGB foreground colors.
    # Textual's NO_COLOR filter changes those IDs and makes images disappear.
    os.environ.pop("NO_COLOR", None)
    with tempfile.TemporaryDirectory(prefix="imagepick-") as temporary:
        create_app(args.screenshots_dir.expanduser(), Path(temporary), source=args.source,
                   limit=args.limit, renderer=args.renderer).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
