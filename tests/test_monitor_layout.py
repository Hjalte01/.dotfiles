import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "monitor_layout", Path(__file__).resolve().parents[1] / "scripts/monitor-layout.py"
)
layout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout)


def monitor(name, x=0, y=0, width=1920, height=1080, scale=1, transform=0):
    return dict(name=name, x=x, y=y, width=width, height=height,
                scale=scale, transform=transform, refreshRate=60.0)


class GeometryTests(unittest.TestCase):
    def test_positions_use_scaled_and_rotated_dimensions(self):
        anchor = monitor("laptop", width=3840, height=2160, scale=2, transform=1)
        external = monitor("external", width=2560, height=1440)
        layout.place(external, anchor, "right")
        self.assertEqual((external["x"], external["y"]), (1080, 0))
        layout.place(external, anchor, "left")
        self.assertEqual(external["x"], -2560)
        layout.place(external, anchor, "down")
        self.assertEqual(external["y"], 1920)
        self.assertEqual(layout.validate([anchor, external]), "")

    def test_partial_shared_edge_allows_vertical_alignment(self):
        self.assertEqual(layout.validate([monitor("a"), monitor("b", x=1920, y=-400)]), "")

    def test_gaps_overlaps_and_corner_only_contact_are_rejected(self):
        for x, y in ((1900, 0), (1930, 0), (1920, 1080)):
            with self.subTest(x=x, y=y):
                self.assertTrue(layout.validate([monitor("a"), monitor("b", x=x, y=y)]))

    def test_three_monitors_require_a_connected_layout(self):
        a, b, c = monitor("a"), monitor("b", x=1920), monitor("c", x=3840)
        self.assertEqual(layout.validate([a, b, c]), "")
        c["x"] += 10
        self.assertTrue(layout.validate([a, b, c]))

    def test_drag_snaps_to_shared_edge_and_preserves_vertical_offset(self):
        a, b = monitor("a"), monitor("b", x=1980, y=-240)
        layout.snap(b, [a, b])
        self.assertEqual((b["x"], b["y"]), (1920, -240))
        self.assertEqual(layout.validate([a, b]), "")

    def test_snap_avoids_a_third_monitor(self):
        a, b, c = monitor("a"), monitor("b", x=1920), monitor("c", x=1900, y=30)
        layout.snap(c, [a, b, c])
        self.assertFalse(layout.overlap(c, a))
        self.assertFalse(layout.overlap(c, b))


class PersistenceTests(unittest.TestCase):
    def test_monitor_json_with_configerror_status_is_still_readable(self):
        import subprocess
        response = subprocess.CompletedProcess([], 0, '[{"solitaryBlockedBy": ["CONFIGERROR"]}]', "")
        with patch.object(layout.subprocess, "run", return_value=response):
            self.assertEqual(layout.hyprctl("monitors", "-j"), response.stdout)

    def test_saved_source_uses_preferred_mode_and_preserves_geometry(self):
        m = monitor("DP-1", x=-1080, y=-100, width=3840, height=2160, scale=2, transform=1)
        original = copy.deepcopy(m)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "hypr/monitor-layout.conf"
            with patch.object(layout, "LAYOUT", path):
                layout.save([m])
            self.assertIn("monitor = DP-1, preferred, -1080x-100, 2, transform, 1", path.read_text())
            self.assertNotIn("3840x2160", path.read_text())
            self.assertFalse(path.with_suffix(".tmp").exists())
        self.assertEqual(m, original)

    def test_migration_updates_generated_modes_and_preserves_other_content(self):
        original = (
            "# Saved by monitor-layout. Edit with Super+T, then P.\n"
            "# Keep the left monitor's offset and rotation.\n"
            "monitor = eDP-1, 1920x1200@60.00300, 0x0, 1, transform, 0\n"
            "monitor = DP-1, 3840x2160@59.95100, -1080x-100, 2, transform, 1\n"
            "monitor = HDMI-A-1, 1920x1080, 1920x0, 1, transform, 0\n"
            "# A mode mentioned in a comment stays 2560x1440@60.\n"
        )
        expected = original.replace(
            ", 1920x1200@60.00300,", ", preferred,"
        ).replace(
            ", 3840x2160@59.95100,", ", preferred,"
        ).replace(
            ", 1920x1080,", ", preferred,"
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "monitor-layout.conf"
            path.write_text(original)
            with patch.object(layout, "LAYOUT", path), patch.object(layout, "hyprctl") as command:
                layout.migrate_saved_modes()
                self.assertEqual(path.read_text(), expected)
                layout.migrate_saved_modes()
            self.assertEqual(path.read_text(), expected)
            command.assert_not_called()
            self.assertFalse(path.with_suffix(".tmp").exists())

    def test_migration_leaves_missing_empty_and_handwritten_files_untouched(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "monitor-layout.conf"
            with patch.object(layout, "LAYOUT", path), patch.object(layout, "hyprctl") as command:
                layout.migrate_saved_modes()
                self.assertFalse(path.exists())
                for contents in (
                    "",
                    "# My custom modes\nmonitor = DP-1, 3840x2160@60, -1920x0, 2\n",
                ):
                    with self.subTest(contents=contents):
                        path.write_text(contents)
                        layout.migrate_saved_modes()
                        self.assertEqual(path.read_text(), contents)
            command.assert_not_called()

    def test_batch_parks_monitors_before_exchanging_sides(self):
        original = [monitor("a"), monitor("b", x=-1920)]
        desired = [monitor("a"), monitor("b", x=1920)]
        with patch.object(layout, "hyprctl") as command:
            layout.apply_rules(desired, original)
        args = command.call_args.args
        self.assertEqual(args[0], "--batch")
        commands = args[1].split("; ")
        self.assertEqual(len(commands), 4)
        self.assertIn("1920x0", commands[-1])
        self.assertIn("13840x0", commands[0])
        self.assertTrue(all("1920x1080@60.00000" in cmd for cmd in commands))
        self.assertNotIn("preferred", args[1])

    def test_hotplug_before_apply_is_rejected(self):
        with patch.object(layout, "discover", return_value=[monitor("a")]):
            with self.assertRaisesRegex(RuntimeError, "Connected screens changed"):
                layout.apply([monitor("a"), monitor("b", x=1920)])

    def test_discovery_excludes_virtual_and_mirrored_outputs(self):
        import json
        outputs = [monitor("eDP-1"), monitor("idle"), dict(monitor("DP-1"), mirrorOf="eDP-1")]
        with patch.object(layout, "hyprctl", return_value=json.dumps(outputs)):
            self.assertEqual([m["name"] for m in layout.discover()], ["eDP-1"])


class PreviewTests(unittest.TestCase):
    def editor(self, keys):
        from unittest.mock import Mock
        original = [monitor("a"), monitor("b", x=1920)]
        screen = Mock()
        screen.getch.side_effect = keys
        with patch.object(layout, "discover", return_value=original):
            editor = layout.Editor(screen)
        editor.draw = lambda: None
        return editor, original

    def run_editor(self, editor):
        from contextlib import ExitStack
        with ExitStack() as stack:
            for name in ("curs_set", "mousemask", "mouseinterval"):
                stack.enter_context(patch.object(layout.curses, name))
            stack.enter_context(patch.object(layout.curses, "has_colors", return_value=False))
            editor.run()

    def test_escape_reverts_preview_without_saving(self):
        editor, original = self.editor([10, 27, ord("q")])
        with patch.object(layout, "discover", return_value=original), \
                patch.object(layout, "apply") as apply, \
                patch.object(layout, "apply_rules") as restore, \
                patch.object(layout, "save") as save:
            self.run_editor(editor)
        apply.assert_called_once()
        restore.assert_called_once()
        save.assert_not_called()

    def test_keep_saves_and_does_not_revert(self):
        editor, original = self.editor([10, 10, ord("q")])
        with patch.object(layout, "discover", return_value=original), \
                patch.object(layout, "apply"), patch.object(layout, "apply_rules") as restore, \
                patch.object(layout, "save") as save:
            self.run_editor(editor)
        save.assert_called_once()
        restore.assert_not_called()

    def test_escape_restores_exact_original_mode(self):
        editor, original = self.editor([10, 27, ord("q")])
        original[1].update(width=2560, height=1440, refreshRate=59.951)
        editor.original = copy.deepcopy(original)
        editor.monitors = copy.deepcopy(original)
        editor.monitors[1]["y"] = -100
        with patch.object(layout, "discover", return_value=original), \
                patch.object(layout, "apply"), patch.object(layout, "hyprctl") as command:
            self.run_editor(editor)
        self.assertIn("b, 2560x1440@59.95100, 1920x0, 1", command.call_args.args[1])
        self.assertNotIn("preferred", command.call_args.args[1])

    def test_timeout_reverts(self):
        editor, original = self.editor([10, -1, ord("q")])
        with patch.object(layout, "discover", return_value=original), \
                patch.object(layout, "apply"), patch.object(layout, "apply_rules") as restore, \
                patch.object(layout, "save") as save, \
                patch.object(layout.time, "monotonic", side_effect=[100, 116]):
            self.run_editor(editor)
        restore.assert_called_once()
        save.assert_not_called()

    def test_interrupt_during_preview_restores_original(self):
        editor, original = self.editor([10, KeyboardInterrupt])
        with patch.object(layout, "discover", return_value=original), \
                patch.object(layout, "apply"), patch.object(layout, "apply_rules") as restore:
            with self.assertRaises(KeyboardInterrupt):
                self.run_editor(editor)
        restore.assert_called_once()


if __name__ == "__main__":
    unittest.main()
