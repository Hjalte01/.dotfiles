import importlib.util
from pathlib import Path
import unittest


spec = importlib.util.spec_from_file_location(
    "glance", Path(__file__).resolve().parents[1] / "scripts/glance.py"
)
glance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(glance)


class GlanceKeysTests(unittest.TestCase):
    def test_releasing_either_part_of_shortcut_closes_peek(self):
        for key in ("q", "Super_L", "Super_R"):
            with self.subTest(key=key):
                keys = glance.PopupKeys(hold=True)
                self.assertTrue(keys.release(key))

    def test_shortcut_autorepeat_keeps_peek_open(self):
        keys = glance.PopupKeys(hold=True)
        for _ in range(5):
            self.assertFalse(keys.press("q"))
        self.assertFalse(keys.pinned)

    def test_pin_survives_escape_autorepeat_and_shortcut_releases(self):
        keys = glance.PopupKeys(hold=True)
        self.assertFalse(keys.press("Escape"))
        self.assertTrue(keys.pinned)
        for key in ("Escape", "Escape", "q", "q"):
            self.assertFalse(keys.press(key))
        for key in ("q", "Super_L", "Escape"):
            self.assertFalse(keys.release(key))
        self.assertTrue(keys.press("a"))

    def test_fresh_escape_or_shortcut_key_closes_pin(self):
        for key in ("Escape", "q", "Super_L", "Super_R"):
            with self.subTest(key=key):
                keys = glance.PopupKeys(hold=True)
                keys.press("Escape")
                keys.release(key)
                self.assertTrue(keys.press(key))

    def test_other_key_closes_pin_even_before_shortcut_released(self):
        keys = glance.PopupKeys(hold=True)
        keys.press("Escape")
        self.assertTrue(keys.press("space"))

    def test_command_opens_pinned_and_any_key_closes_it(self):
        for key in ("a", "q", "Escape", "Super_L", "Shift_L"):
            with self.subTest(key=key):
                keys = glance.PopupKeys()
                self.assertTrue(keys.pinned)
                self.assertTrue(keys.press(key))


if __name__ == "__main__":
    unittest.main()
