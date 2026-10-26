import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch


spec = importlib.util.spec_from_file_location(
    "app_launcher", Path(__file__).resolve().parents[1] / "scripts/app-launcher.py"
)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def app(app_id, name):
    info = Mock()
    info.get_boolean.return_value = False
    return {"id": app_id, "name": name, "icon": "test", "meta": "", "info": info}


class OrderingTests(unittest.TestCase):
    def test_popular_lower_priority_apps_never_overtake_normal_apps(self):
        apps = [app("roblox.desktop", "Roblox"), app("editor.desktop", "Editor"),
                app("browser.desktop", "Browser"), app("net.lutris.Lutris.desktop", "Lutris")]
        history = {"roblox.desktop": 999, "net.lutris.Lutris.desktop": 100, "editor.desktop": 10}
        result = launcher.ordered(apps, {}, history)
        self.assertEqual([item["name"] for item in result], ["Editor", "Browser", "Roblox", "Lutris"])

    def test_explicit_normal_overrides_default_and_new_apps_default_normal(self):
        self.assertFalse(launcher.is_low("roblox.desktop", {"roblox.desktop": "normal"}))
        self.assertFalse(launcher.is_low("new-app.desktop", {}))
        self.assertTrue(launcher.is_low("editor.desktop", {"editor.desktop": "low"}))

    def test_history_import_and_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state/history.json"
            cache = Path(directory) / "druncache"
            cache.write_text("200 browser.desktop\n48 net.lutris.Lutris.desktop\ninvalid\n")
            with patch.object(launcher, "STATE", state), patch.object(launcher, "CACHE", cache):
                history = launcher.load_history()
                self.assertEqual(history["browser.desktop"], 200)
                launcher.write_json(state, {"editor.desktop": 5})
                self.assertEqual(launcher.load_history(), {"editor.desktop": 5})

    def test_overrides_persist_without_changing_defaults_for_other_apps(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "priorities.json"
            launcher.write_json(config, {"roblox.desktop": "normal", "browser.desktop": "low"})
            overrides = launcher.read_json(config)
            self.assertFalse(launcher.is_low("roblox.desktop", overrides))
            self.assertTrue(launcher.is_low("browser.desktop", overrides))
            self.assertTrue(launcher.is_low("net.lutris.Lutris.desktop", overrides))


class LaunchTests(unittest.TestCase):
    def test_live_menu_arguments_have_no_conflicting_bindings(self):
        result = subprocess.run(
            ["rofi", *launcher.menu_command()[1:], "-dump", "-filter", "roblox"],
            input=launcher.rows([app("roblox.desktop", "Roblox")]),
            text=True, capture_output=True, check=True, timeout=5,
        )
        self.assertEqual(result.stdout, "0\nroblox\n")

    def test_terminal_launch_preserves_exec_field_codes_and_working_directory(self):
        from gi.repository import Gio

        with tempfile.TemporaryDirectory() as directory:
            desktop = Path(directory) / "test.desktop"
            desktop.write_text('[Desktop Entry]\nType=Application\nName=Test\n'
                               'Exec=echo "two words" %F\nTerminal=true\nPath=/tmp\n')
            info = Gio.DesktopAppInfo.new_from_filename(str(desktop))
            with patch.object(Gio.DesktopAppInfo, "launch") as start:
                launcher.launch_app(info)
            start.assert_called_once_with([], None)
            with patch.object(Gio.DesktopAppInfo, "new_from_keyfile", wraps=Gio.DesktopAppInfo.new_from_keyfile) as create, \
                 patch.object(Gio.DesktopAppInfo, "launch"):
                launcher.launch_app(info)
            keyfile = create.call_args.args[0]
            self.assertEqual(keyfile.get_string("Desktop Entry", "Exec"), 'ghostty -e echo "two words" %F')
            self.assertEqual(keyfile.get_string("Desktop Entry", "Path"), "/tmp")
            self.assertFalse(keyfile.get_boolean("Desktop Entry", "Terminal"))

    def test_cancel_does_not_launch_or_write_history(self):
        item = app("editor.desktop", "Editor")
        with patch.object(launcher, "discover", return_value=[item]), \
             patch.object(launcher.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "")), \
             patch.object(launcher, "write_json") as save:
            launcher.launch()
        item["info"].launch.assert_not_called()
        save.assert_not_called()

    def test_selection_uses_original_index_in_sorted_list(self):
        game = app("roblox.desktop", "Roblox")
        editor = app("editor.desktop", "Editor")
        with patch.object(launcher, "discover", return_value=[game, editor]), \
             patch.object(launcher, "read_json", return_value={}), \
             patch.object(launcher, "load_history", return_value={}), \
             patch.object(launcher.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "1\n")), \
             patch.object(launcher, "write_json") as save:
            launcher.launch()
        game["info"].launch.assert_called_once_with([], None)
        editor["info"].launch.assert_not_called()
        self.assertEqual(save.call_args.args[1], {"roblox.desktop": 1})

    def test_actual_rofi_filter_retains_tiers_and_keywords(self):
        apps = [app("editor.desktop", "Example Editor"), app("roblox.desktop", "Example Roblox")]
        apps[0]["meta"] = "writing"
        apps[1]["meta"] = "gaming"
        data = launcher.rows(apps)
        command = ["rofi", "-no-config", "-dmenu", "-no-sort", "-i", "-dump", "-filter"]
        result = subprocess.run(command + ["example"], input=data, text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout.splitlines(), ["Example Editor writing", "Example Roblox gaming"])
        result = subprocess.run(command + ["gaming"], input=data, text=True, capture_output=True, check=True, timeout=10)
        self.assertEqual(result.stdout.strip(), "Example Roblox gaming")

    def test_desktop_strings_cannot_inject_rows_or_metadata(self):
        self.assertEqual(launcher.clean("one\ntwo\0icon\x1fthree"), "one two icon three")


class InlinePriorityTests(unittest.TestCase):
    def test_toggle_preserves_query_and_selected_app_without_launching(self):
        editor = app("editor.desktop", "Editor")
        browser = app("browser.desktop", "Browser")
        responses = [subprocess.CompletedProcess([], 10, "0\nedit\n"),
                     subprocess.CompletedProcess([], 10, "1\nedit\n"),
                     subprocess.CompletedProcess([], 1, "")]
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(launcher, "CONFIG", Path(directory) / "priorities.json"), \
             patch.object(launcher, "discover", return_value=[editor, browser]), \
             patch.object(launcher, "load_history", return_value={"editor.desktop": 20}), \
             patch.object(launcher.subprocess, "run", side_effect=responses) as run:
            launcher.launch()
            self.assertEqual(launcher.read_json(launcher.CONFIG), {"editor.desktop": "normal"})
        second, third = run.call_args_list[1:]
        self.assertEqual(second.args[0][second.args[0].index("-filter") + 1], "edit")
        self.assertEqual(second.args[0][second.args[0].index("-selected-row") + 1], "1")
        self.assertIn('foreground="#888888"', second.kwargs["input"])
        self.assertNotIn('foreground="#888888"', third.kwargs["input"])
        editor["info"].launch.assert_not_called()
        browser["info"].launch.assert_not_called()

    def test_help_toggles_even_without_a_matching_app(self):
        responses = [subprocess.CompletedProcess([], 11, "-1\nno match\n"),
                     subprocess.CompletedProcess([], 11, "-1\nno match\n"),
                     subprocess.CompletedProcess([], 1, "")]
        with patch.object(launcher, "discover", return_value=[app("editor.desktop", "Editor")]), \
             patch.object(launcher.subprocess, "run", side_effect=responses) as run, \
             patch.object(launcher, "write_json") as save:
            launcher.launch()
        second, third = run.call_args_list[1:]
        self.assertIn("toggle selected app", second.args[0][-1])
        self.assertNotIn("toggle selected app", third.args[0][-1])
        self.assertEqual(second.args[0][second.args[0].index("-filter") + 1], "no match")
        save.assert_not_called()

    def test_toggle_with_no_selection_does_not_change_priorities(self):
        with patch.object(launcher, "discover", return_value=[app("editor.desktop", "Editor")]), \
             patch.object(launcher.subprocess, "run", side_effect=[
                 subprocess.CompletedProcess([], 10, "-1\nnone\n"),
                 subprocess.CompletedProcess([], 1, "")]), \
             patch.object(launcher, "write_json") as save:
            launcher.launch()
        save.assert_not_called()

    def test_priority_dot_escapes_app_names_and_leaves_search_text_clean(self):
        row = launcher.rows([app("roblox.desktop", "Roblox <Tools> & More")])
        search, metadata = row.split("\0", 1)
        self.assertNotIn("·", search)
        self.assertIn("Roblox &lt;Tools&gt; &amp; More", metadata)
        self.assertIn('foreground="#888888" size="small">·</span>', metadata)
        self.assertNotIn("·", launcher.rows([app("roblox.desktop", "Roblox")], {"roblox.desktop": "normal"}))


if __name__ == "__main__":
    unittest.main()
