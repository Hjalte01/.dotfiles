"""Exercise selection persistence and config preservation in an isolated home."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("theme_assets", REPO / "scripts/theme-assets.py")
assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assets)


class ThemeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.config = self.home / ".config"
        self.state = self.home / ".local/state/dotfiles-theme"
        self.catalog = self.config / "dotfiles-theme/catalog"
        self.catalog.mkdir(parents=True)
        palettes = json.loads((REPO / "themes/palettes.json").read_text())
        (self.catalog / "palettes.json").write_text(json.dumps(palettes))
        (self.catalog / "wallpapers.json").write_text(json.dumps(assets.WALLPAPERS))
        for key, palette in palettes.items():
            directory = self.catalog / key
            directory.mkdir()
            for name, contents in assets.files(palette):
                (directory / name).write_text(contents)
            for name, _ in assets.WALLPAPERS:
                (directory / f"{name}.png").write_bytes(b"test-image")
        self.env = {**os.environ, "HOME":str(self.home), "XDG_CONFIG_HOME":str(self.config),
                    "XDG_STATE_HOME":str(self.home / ".local/state"), "DOTFILES_THEME_DESKTOP":"1"}
        self.env.pop("WAYLAND_DISPLAY", None)

    def command(self, *args, ok=True, env=None):
        result = subprocess.run([os.environ.get("SYSTEM_THEME_BIN", "system-theme"), *args, "--no-reload"], env=env or self.env, capture_output=True, text=True)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def test_switch_all_palettes_preserves_preferences_and_backups(self):
        path = self.config / "btop/btop.conf"
        path.parent.mkdir(parents=True)
        original = 'color_theme = "Default"\nupdate_ms = 750\n'
        path.write_text(original)
        for key in json.loads((self.catalog / "palettes.json").read_text()):
            self.command("set", key)
            current = self.config / "dotfiles-theme/current"
            self.assertEqual(current.resolve(), self.catalog / key)
            self.assertIn('update_ms = 750', path.read_text())
            self.assertIn('color_theme = "dotfiles"', path.read_text())
            self.assertEqual(path.with_name(path.name + ".before-system-theme").read_text(), original)
            self.assertEqual((self.state / "wallpaper").resolve(), self.catalog / key / "alpine.png")
        self.command("apply")
        self.assertEqual(path.read_text().count("color_theme ="), 1)

    def test_custom_wallpaper_is_copied_and_remembered_per_theme(self):
        image = self.home / 'wall paper $(literal).png'
        image.write_bytes(b"personal image")
        self.command("apply")
        self.command("wallpaper", str(image))
        remembered = (self.state / "wallpaper").resolve()
        image.unlink()
        self.command("set", "nord")
        self.command("wallpaper", "orbit")
        self.command("set", "mocha")
        self.assertEqual((self.state / "wallpaper").resolve(), remembered)
        self.assertEqual(remembered.read_bytes(), b"personal image")
        self.command("set", "nord")
        self.assertEqual((self.state / "wallpaper").resolve(), self.catalog / "nord/orbit.png")

    def test_bad_theme_and_cancelled_preview_leave_saved_state_untouched(self):
        self.command("apply")
        original = (self.state / "state.json").read_text()
        self.command("set", "../../invalid", ok=False)
        self.command("preview", "nord")
        self.assertEqual((self.state / "state.json").read_text(), original)
        self.assertEqual((self.config / "dotfiles-theme/current").resolve(), self.catalog / "nord")
        self.command("cancel")
        self.assertEqual((self.config / "dotfiles-theme/current").resolve(), self.catalog / "mocha")
        self.assertEqual((self.state / "state.json").read_text(), original)

    def test_wallpaper_cycle_includes_new_styles_and_wraps(self):
        self.command("apply")
        names = [name for name, _ in assets.WALLPAPERS]
        for name in names[1:] + names[:1]:
            self.command("wallpaper-next")
            self.assertEqual((self.state / "wallpaper").resolve(), self.catalog / "mocha" / f"{name}.png")
        self.command("wallpaper", "lagoon")
        self.command("set", "latte")
        self.command("wallpaper", "bloom")
        self.command("set", "mocha")
        self.assertEqual((self.state / "wallpaper").resolve(), self.catalog / "mocha/lagoon.png")
        self.command("set", "latte")
        self.assertEqual((self.state / "wallpaper").resolve(), self.catalog / "latte/bloom.png")

    def test_obsidian_and_gtk_keep_unrelated_preferences(self):
        vault = self.home / "notes/.obsidian"
        vault.mkdir(parents=True)
        registry = self.config / "obsidian/obsidian.json"
        registry.parent.mkdir()
        registry.write_text(json.dumps({"vaults":{"test":{"path":str(vault.parent)}}}))
        appearance = vault / "appearance.json"
        appearance.write_text(json.dumps({"enabledCssSnippets":["personal"], "baseFontSize":18}))
        gtk = self.config / "gtk-3.0/gtk.css"
        gtk.parent.mkdir()
        gtk.write_text("button { padding: 8px; }\n")
        self.command("set", "latte")
        self.command("apply")
        prefs = json.loads(appearance.read_text())
        self.assertEqual(prefs["enabledCssSnippets"], ["personal", "dotfiles-theme"])
        self.assertEqual(prefs["baseFontSize"], 18)
        self.assertEqual(prefs["theme"], "moonstone")
        self.assertEqual(gtk.read_text().count("@import"), 1)
        self.assertIn("button { padding: 8px; }", gtk.read_text())

    def test_shared_host_has_no_desktop_side_effects(self):
        self.command("set", "nord", env={**self.env, "DOTFILES_THEME_DESKTOP":"0"})
        self.assertFalse((self.config / "gtk-3.0").exists())
        self.assertFalse((self.config / "qt6ct").exists())
        self.assertFalse((self.state / "wallpaper").exists())


if __name__ == "__main__":
    unittest.main()
