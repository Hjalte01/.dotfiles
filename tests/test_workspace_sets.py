"""Exercise workspace isolation and interrupted switches with a fake compositor."""

import copy
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


loader = importlib.machinery.SourceFileLoader("workspace_set", str(Path(__file__).parents[1] / "scripts/workspace-set"))
spec = importlib.util.spec_from_loader(loader.name, loader)
ws = importlib.util.module_from_spec(spec)
loader.exec_module(ws)


class Compositor:
    def __init__(self):
        self.workspaces = [{"id": 2, "name": "2", "monitor": "eDP-1"},
                           {"id": 3, "name": "3", "monitor": "eDP-1"}]
        self.monitors = [{"name": "eDP-1", "focused": True,
                          "activeWorkspace": {"id": 3, "name": "3"}}]
        self.clients = [{"address": "0xschool", "mapped": True, "workspace": {"id": 2, "name": "2"}},
                        {"address": "0xcurrent", "mapped": True, "workspace": {"id": 3, "name": "3"}}]
        self.active = "0xcurrent"
        self.calls = []
        self.fail_action = None

    def query(self, subject):
        return copy.deepcopy({"workspaces": self.workspaces, "monitors": self.monitors,
                              "clients": self.clients, "activewindow": {"address": self.active}}[subject])

    def dispatch(self, action, argument):
        self.calls.append((action, argument))
        if self.fail_action == action:
            self.fail_action = None
            raise RuntimeError("injected failure")
        if action == "renameworkspace":
            wid, name = argument.split(" ", 1)
            wid = int(wid)
            assert not any(w["name"] == name and w["id"] != wid for w in self.workspaces), "duplicate slot name"
            for item in [*self.workspaces, *(m["activeWorkspace"] for m in self.monitors),
                         *(c["workspace"] for c in self.clients)]:
                if item["id"] == wid:
                    item["name"] = name
        elif action == "focusmonitor":
            for monitor in self.monitors:
                monitor["focused"] = monitor["name"] == argument
        elif action == "focusworkspaceoncurrentmonitor":
            name = argument.removeprefix("name:")
            monitor = next(m for m in self.monitors if m["focused"])
            target = next((w for w in self.workspaces if w["name"] == name), None)
            if target is None:
                target = {"id": -100 - len(self.workspaces), "name": name, "monitor": monitor["name"]}
                self.workspaces.append(target)
            # Swap visible workspaces when the target is on another output.
            for other in self.monitors:
                if other != monitor and other["activeWorkspace"]["id"] == target["id"]:
                    other["activeWorkspace"] = copy.deepcopy(monitor["activeWorkspace"])
            monitor["activeWorkspace"] = {"id": target["id"], "name": name}
            target["monitor"] = monitor["name"]
        elif action == "focuswindow":
            self.active = argument.removeprefix("address:")
            client = next(c for c in self.clients if c["address"] == self.active)
            self.dispatch("focusworkspaceoncurrentmonitor", "name:" + client["workspace"]["name"])
        else:
            raise AssertionError(f"Unexpected dispatcher: {action}")


class WorkspaceSetsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.compositor = Compositor()
        for mock in (patch.object(ws, "STATE", Path(self.temporary.name) / "state.json"),
                     patch.object(ws, "query", self.compositor.query),
                     patch.object(ws, "dispatch", self.compositor.dispatch),
                     patch.object(ws, "refresh_bar"),
                     patch.dict(os.environ, {"HYPRLAND_INSTANCE_SIGNATURE": "test-session"})):
            mock.start()
            self.addCleanup(mock.stop)

    def test_round_trip_preserves_window_workspace_ids_and_focus(self):
        before = {c["address"]: c["workspace"]["id"] for c in self.compositor.clients}
        ws.mutate("switch", "School")
        self.assertEqual(ws.read_state()["current"], "school")
        self.assertTrue(all(c["workspace"]["name"].startswith("set:current:") for c in self.compositor.clients))
        self.assertEqual(self.compositor.monitors[0]["activeWorkspace"]["name"], "2")
        # Simulate a new app opened while School is active.
        self.compositor.clients.append({"address": "0xnew", "workspace": copy.deepcopy(self.compositor.monitors[0]["activeWorkspace"])})
        ws.mutate("back")
        self.assertEqual(self.compositor.monitors[0]["activeWorkspace"]["name"], "3")
        self.assertEqual(self.compositor.active, "0xcurrent")
        for client in self.compositor.clients[:2]:
            self.assertEqual(client["workspace"]["id"], before[client["address"]])
        self.assertEqual(self.compositor.clients[-1]["workspace"]["name"], "set:school:2")
        ws.mutate("back")
        self.assertEqual(self.compositor.clients[-1]["workspace"]["name"], "2")

    def test_failure_after_new_slot_is_created_restores_source(self):
        ws.mutate("switch", "School")
        ws.mutate("back")
        # Include a second output to fail after creating one destination slot.
        self.compositor.monitors.append({"name": "DP-1", "focused": False,
                                         "activeWorkspace": {"id": 2, "name": "2"}})
        original = self.compositor.dispatch
        count = 0

        def fail_after_slot(action, arg):
            nonlocal count
            if action == "focusworkspaceoncurrentmonitor":
                count += 1
                if count == 2:
                    raise RuntimeError("output disconnected")
            original(action, arg)

        with patch.object(ws, "dispatch", fail_after_slot):
            with self.assertRaisesRegex(RuntimeError, "output disconnected"):
                ws.mutate("switch", "Fun")
        self.assertEqual(ws.read_state()["current"], "current")
        self.assertNotIn("pending", ws.read_state())
        self.assertEqual(self.compositor.clients[0]["workspace"]["name"], "2")
        self.assertEqual(self.compositor.clients[1]["workspace"]["name"], "3")

    def test_failure_while_restoring_existing_destination_rolls_back(self):
        ws.mutate("switch", "School")
        self.compositor.fail_action = "focusmonitor"
        with self.assertRaises(RuntimeError):
            ws.mutate("back")
        self.assertEqual(ws.read_state()["current"], "school")
        self.assertNotIn("pending", ws.read_state())
        self.assertEqual(self.compositor.clients[0]["workspace"]["name"], "set:current:2")

    def test_idle_workspace_is_shared(self):
        self.compositor.workspaces.append({"id": -50, "name": "10", "monitor": "idle"})
        ws.mutate("switch", "Fun")
        self.assertEqual(self.compositor.workspaces[-2]["name"], "10")
        self.assertFalse(any(arg.startswith("-50 ") for action, arg in self.compositor.calls if action == "renameworkspace"))

    def test_interrupted_switch_is_recovered_by_next_command(self):
        original = self.compositor.dispatch

        def interrupt(action, arg):
            original(action, arg)
            if action == "renameworkspace":
                raise KeyboardInterrupt()

        with patch.object(ws, "dispatch", interrupt):
            with self.assertRaises(KeyboardInterrupt):
                ws.mutate("switch", "School")
        self.assertIn("pending", ws.read_state())
        state = ws.load()
        self.assertNotIn("pending", state)
        self.assertEqual(state["current"], "current")
        self.assertEqual([c["workspace"]["name"] for c in self.compositor.clients], ["2", "3"])
        self.assertEqual(self.compositor.monitors[0]["activeWorkspace"]["name"], "3")

    def test_create_rename_duplicate_and_session_reset(self):
        ws.mutate("create", "Exam project")
        target = ws.read_state()["current"]
        ws.mutate("rename", "Exam prep")
        with self.assertRaises(RuntimeError):
            ws.mutate("create", "sChOoL")
        with self.assertRaises(RuntimeError):
            ws.mutate("rename", "School")
        with patch.dict(os.environ, {"HYPRLAND_INSTANCE_SIGNATURE": "new-session"}):
            state = ws.load()
        self.assertEqual(state["current"], target)
        self.assertEqual(state["sets"][target]["name"], "Exam prep")
        self.assertIsNone(state["previous"])
        self.assertNotIn("window", state["sets"]["current"])

    def test_connected_monitors_have_unique_slots(self):
        self.compositor.monitors.append({"name": "DP-1", "focused": False,
                                         "activeWorkspace": {"id": 2, "name": "2"}})
        ws.mutate("switch", "Fun")
        self.assertEqual({m["activeWorkspace"]["name"] for m in self.compositor.monitors}, {"1", "2"})
        ws.mutate("back")
        self.assertEqual([m["activeWorkspace"]["name"] for m in self.compositor.monitors], ["3", "2"])

    def test_negative_ids_are_not_parsed_as_cli_flags(self):
        with patch.object(ws, "run", return_value="ok") as run, patch.object(ws, "dispatch", self.original_dispatch):
            ws.dispatch("renameworkspace", "-1337 2")
        run.assert_called_once_with("hyprctl", "--", "dispatch", "renameworkspace", "-1337 2")

    original_dispatch = staticmethod(ws.dispatch)


if __name__ == "__main__":
    unittest.main()
