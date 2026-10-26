"""Run the workspace shortcut against a stateful, isolated fake compositor."""

import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


DISPATCHER = Path(__file__).resolve().parents[1] / "scripts/workspace-dispatch"
FAKE_HYPRCTL = r'''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

path = Path(os.environ["FAKE_HYPR_STATE"])
state = json.loads(path.read_text())
args = [arg for arg in sys.argv[1:] if arg not in ("--", "-j")]

def monitor(name):
    return next(m for m in state["monitors"] if m["name"] == name and not m.get("disabled"))

def workspace(selector):
    if selector.startswith("name:"):
        name = selector.removeprefix("name:")
        target = next((w for w in state["workspaces"] if w["name"] == name), None)
    else:
        target = next((w for w in state["workspaces"] if str(w["id"]) == selector), None)
        name = selector
    if target is None:
        output = "idle" if name == "10" else next(m["name"] for m in state["monitors"] if m["focused"])
        target = {"id": -2000 - len(state["workspaces"]), "name": name, "monitor": output}
        state["workspaces"].append(target)
    return target

def select_monitor(name):
    selected = monitor(name)
    for output in state["monitors"]:
        output["focused"] = output is selected
    wid = selected["activeWorkspace"]["id"]
    state["active"] = next((c["address"] for c in state["clients"] if c["workspace"]["id"] == wid), None)

def select_workspace(target):
    monitor(target["monitor"])["activeWorkspace"] = {"id": target["id"], "name": target["name"]}
    select_monitor(target["monitor"])

if args[0] == "monitors":
    answer = state["monitors"] if "all" in args else [m for m in state["monitors"] if not m.get("disabled")]
elif args[0] == "workspaces":
    answer = state["workspaces"]
elif args[0] == "activewindow":
    answer = next((c for c in state["clients"] if c["address"] == state["active"]), {})
elif args[0] == "dispatch":
    action, argument = args[1:]
    state["calls"].append([action, argument])
    if action == "focusmonitor":
        select_monitor(argument)
    elif action == "workspace":
        select_workspace(workspace(argument))
    elif action == "moveworkspacetomonitor":
        selector, destination = argument.split()
        target = workspace(selector)
        source = monitor(target["monitor"])
        target["monitor"] = destination
        if source["activeWorkspace"]["id"] == target["id"]:
            replacement = workspace("name:10")
            source["activeWorkspace"] = {"id": replacement["id"], "name": replacement["name"]}
        # Moving a visible workspace may also change the compositor's active
        # window. A subsequent window move must address its captured source.
        select_workspace(target)
    elif action in ("movetoworkspace", "movetoworkspacesilent"):
        selector, _, address = argument.partition(",address:")
        target = workspace(selector)
        address = address or state["active"]
        client = next(c for c in state["clients"] if c["address"] == address)
        client["workspace"] = {"id": target["id"], "name": target["name"]}
        if action == "movetoworkspace":
            select_workspace(target)
    elif action == "focuswindow":
        address = argument.removeprefix("address:")
        client = next(c for c in state["clients"] if c["address"] == address)
        select_workspace(workspace("name:" + client["workspace"]["name"]))
        state["active"] = address
    else:
        raise AssertionError("Unexpected dispatch: " + action)
    answer = "ok"
else:
    raise AssertionError("Unexpected hyprctl arguments: " + repr(args))
path.write_text(json.dumps(state))
print(json.dumps(answer) if answer != "ok" else answer)
'''


class WorkspaceDispatchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.state_path = self.directory / "compositor.json"
        executable = self.directory / "hyprctl"
        executable.write_text(FAKE_HYPRCTL)
        executable.chmod(0o755)
        # Override the absolute helper as a shell function; tests must never
        # call the running desktop's key-hint service.
        shell_environment = self.directory / "bash-env"
        shell_environment.write_text("function /home/hjalte/.local/bin/desktop-which-key { :; }\n")
        self.environment = dict(os.environ, PATH=f"{self.directory}:{os.environ['PATH']}",
                                XDG_STATE_HOME=str(self.directory / "state"),
                                FAKE_HYPR_STATE=str(self.state_path), BASH_ENV=str(shell_environment))
        self.state = {
            "monitors": [
                {"name": "eDP-1", "focused": True, "activeWorkspace": {"id": -1339, "name": "4"}},
                {"name": "idle", "focused": False, "activeWorkspace": {"id": 3, "name": "3"}},
            ],
            "workspaces": [
                {"id": -1339, "name": "4", "monitor": "eDP-1"},
                {"id": 3, "name": "3", "monitor": "idle"},
            ],
            "clients": [
                {"address": "0xsource", "workspace": {"id": -1339, "name": "4"}},
                {"address": "0xtarget", "workspace": {"id": 3, "name": "3"}},
            ],
            "active": "0xsource", "calls": [],
        }

    def dispatch(self, action, slot):
        self.state_path.write_text(json.dumps(self.state))
        result = subprocess.run(["bash", str(DISPATCHER), action, slot], env=self.environment,
                                text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.state = json.loads(self.state_path.read_text())
        return self.state["calls"]

    def target(self, name):
        return next(w for w in self.state["workspaces"] if w["name"] == name)

    def focused(self):
        return next(m for m in self.state["monitors"] if m["focused"])

    def focus_idle(self):
        self.state["monitors"][0]["focused"] = False
        self.state["monitors"][1]["focused"] = True
        self.state["active"] = "0xtarget"

    def test_switch_recovers_hidden_workspace_without_parking_source(self):
        calls = self.dispatch("switch", "3")
        self.assertIn(["moveworkspacetomonitor", "name:3 eDP-1"], calls)
        self.assertEqual(self.target("3")["monitor"], "eDP-1")
        self.assertEqual(self.target("4")["monitor"], "eDP-1")
        self.assertEqual(self.focused()["activeWorkspace"]["name"], "3")
        self.assertEqual(self.focused()["name"], "eDP-1")

    def test_switch_from_idle_recovers_workspace_on_physical_monitor(self):
        self.focus_idle()
        self.dispatch("switch", "3")
        self.assertEqual(self.focused()["name"], "eDP-1")
        self.assertEqual(self.focused()["activeWorkspace"]["name"], "3")
        self.assertEqual(self.target("4")["monitor"], "eDP-1")

    def test_move_captures_source_before_workspace_recovery_changes_focus(self):
        calls = self.dispatch("move", "3")
        self.assertIn(["movetoworkspace", "name:3,address:0xsource"], calls)
        self.assertEqual(self.state["clients"][0]["workspace"]["name"], "3")
        self.assertEqual(self.state["clients"][1]["workspace"]["name"], "3")
        self.assertEqual(self.focused()["name"], "eDP-1")

    def test_move_from_idle_preserves_captured_source(self):
        self.focus_idle()
        self.state["workspaces"].append({"id": -10, "name": "10", "monitor": "idle"})
        self.state["monitors"][1]["activeWorkspace"] = {"id": -10, "name": "10"}
        self.state["clients"].append({"address": "0xidle", "workspace": {"id": -10, "name": "10"}})
        self.state["active"] = "0xidle"
        calls = self.dispatch("move", "3")
        self.assertIn(["movetoworkspacesilent", "name:3,address:0xidle"], calls)
        self.assertEqual(self.state["clients"][-1]["workspace"]["name"], "3")
        self.assertEqual(self.state["active"], "0xidle")
        self.assertEqual(self.focused()["name"], "eDP-1")

    def test_external_physical_workspace_keeps_normal_switching_behavior(self):
        self.state["monitors"].append({"name": "HDMI-A-1", "focused": False,
                                       "activeWorkspace": {"id": 3, "name": "3"}})
        self.target("3")["monitor"] = "HDMI-A-1"
        self.state["monitors"][1]["activeWorkspace"] = {"id": -10, "name": "10"}
        calls = self.dispatch("switch", "3")
        self.assertNotIn("moveworkspacetomonitor", [action for action, _ in calls])
        self.assertEqual(self.focused()["name"], "HDMI-A-1")

    def test_slot_name_wins_over_numeric_id_of_parked_workspace(self):
        self.target("3")["id"] = -1341
        self.state["clients"][1]["workspace"]["id"] = -1341
        self.state["monitors"][1]["activeWorkspace"]["id"] = -1341
        self.state["workspaces"].append({"id": 3, "name": "set:school:3", "monitor": "eDP-1"})
        self.dispatch("switch", "3")
        self.assertEqual(self.focused()["activeWorkspace"], {"id": -1341, "name": "3"})
        self.assertEqual(self.target("set:school:3")["monitor"], "eDP-1")

    def test_idle_focus_falls_back_when_preferred_laptop_output_is_disabled(self):
        self.focus_idle()
        external = copy.deepcopy(self.state["monitors"][0])
        external.update(name="HDMI-A-1", focused=False)
        self.state["monitors"][0]["disabled"] = True
        self.state["monitors"].append(external)
        self.target("4")["monitor"] = "HDMI-A-1"
        self.dispatch("switch", "3")
        self.assertEqual(self.target("3")["monitor"], "HDMI-A-1")
        self.assertEqual(self.focused()["name"], "HDMI-A-1")

    def test_shared_idle_workspace_still_opens_on_idle_output(self):
        self.state["workspaces"].append({"id": -10, "name": "10", "monitor": "idle"})
        calls = self.dispatch("switch", "10")
        self.assertNotIn("moveworkspacetomonitor", [action for action, _ in calls])
        self.assertEqual(self.focused()["name"], "idle")
        self.assertEqual(self.focused()["activeWorkspace"]["name"], "10")


if __name__ == "__main__":
    unittest.main()
