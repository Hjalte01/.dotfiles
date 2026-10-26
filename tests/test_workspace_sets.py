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
                              "clients": self.clients,
                              "activewindow": next((c for c in self.clients if c["address"] == self.active), {})}[subject])

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
        elif action == "movetoworkspacesilent":
            workspace, address = argument.split(",address:", 1)
            name = workspace.removeprefix("name:")
            target = next((w for w in self.workspaces if w["name"] == name), None)
            client = next(c for c in self.clients if c["address"] == address)
            source = client["workspace"]["id"]
            if target is None:
                target = {"id": -100 - len(self.workspaces), "name": name, "monitor": "eDP-1"}
                self.workspaces.append(target)
            client["workspace"] = {"id": target["id"], "name": name}
            if self.active == address:
                self.active = next((c["address"] for c in self.clients if c["workspace"]["id"] == source), None)
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

    def test_overview_focus_switches_set_then_focuses_workspace_on_destination_monitor(self):
        ws.mutate("switch", "School")
        window_ids = {c["address"]: c["workspace"]["id"] for c in self.compositor.clients}
        self.compositor.calls.clear()
        ws.focus_window("0xcurrent", "eDP-1")
        state = ws.read_state()
        self.assertEqual(state["current"], "current")
        self.assertEqual(state["previous"], "school")
        self.assertEqual(self.compositor.active, "0xcurrent")
        self.assertEqual(self.compositor.monitors[0]["activeWorkspace"]["name"], "3")
        self.assertEqual(window_ids, {c["address"]: c["workspace"]["id"] for c in self.compositor.clients})
        self.assertFalse(any(action == "focusworkspaceoncurrentmonitor" and "set:" in arg
                             for action, arg in self.compositor.calls))

    def test_overview_focus_in_current_set_preserves_previous_set(self):
        ws.mutate("switch", "School")
        ws.mutate("back")
        ws.focus_window("0xschool", "eDP-1")
        self.assertEqual(ws.read_state()["previous"], "school")
        self.assertEqual(self.compositor.active, "0xschool")
        self.assertEqual(self.compositor.monitors[0]["activeWorkspace"]["name"], "2")

    def test_overview_closed_window_or_disconnected_monitor_does_not_switch_sets(self):
        ws.mutate("switch", "School")
        for address, monitor in [("0xclosed", "eDP-1"), ("0xcurrent", "gone")]:
            with self.subTest(address=address, monitor=monitor), self.assertRaises(RuntimeError):
                ws.focus_window(address, monitor)
            self.assertEqual(ws.read_state()["current"], "school")

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

    def test_move_back_uses_previous_focused_workspace_and_preserves_view_and_history(self):
        self.compositor.monitors.append({"name": "DP-1", "focused": False,
                                         "activeWorkspace": {"id": 2, "name": "2"}})
        ws.mutate("switch", "School")
        school_workspace = copy.deepcopy(self.compositor.monitors[0]["activeWorkspace"])
        for address in ("0xfirst", "0xsecond"):
            self.compositor.clients.append({"address": address, "workspace": copy.deepcopy(school_workspace)})
        before = ws.read_state()
        monitors = copy.deepcopy(self.compositor.monitors)
        for address in ("0xfirst", "0xsecond"):
            self.compositor.active = address
            ws.mutate("move-back")
            moved = next(c for c in self.compositor.clients if c["address"] == address)
            self.assertEqual(moved["workspace"], {"id": 3, "name": "set:current:3"})
            self.assertEqual(self.compositor.monitors, monitors)
            self.assertEqual(ws.read_state(), before)
        # The other window on the destination's second monitor is untouched.
        self.assertEqual(self.compositor.clients[0]["workspace"], {"id": 2, "name": "set:current:2"})
        ws.mutate("back")
        self.assertEqual([c["workspace"]["name"] for c in self.compositor.clients[-2:]], ["3", "3"])
        self.assertEqual(self.compositor.monitors[0]["activeWorkspace"]["name"], "3")

    def test_move_back_recreates_empty_destination(self):
        ws.mutate("switch", "School")
        self.compositor.clients = [c for c in self.compositor.clients if c["address"] != "0xcurrent"]
        self.compositor.workspaces = [w for w in self.compositor.workspaces if w["id"] != 3]
        self.compositor.clients.append({"address": "0xnew", "workspace": copy.deepcopy(self.compositor.monitors[0]["activeWorkspace"])})
        self.compositor.active = "0xnew"
        ws.mutate("move-back")
        self.assertEqual(self.compositor.clients[-1]["workspace"]["name"], "set:current:3")
        ws.mutate("back")
        self.assertEqual(self.compositor.clients[-1]["workspace"]["name"], "3")
        self.assertEqual(self.compositor.monitors[0]["activeWorkspace"]["name"], "3")

    def test_move_back_falls_back_to_source_slot_without_saved_focus(self):
        ws.mutate("switch", "School")
        ws.mutate("back")
        state = ws.read_state()
        state["sets"]["school"].pop("focused")
        ws.save(state)
        ws.mutate("move-back")
        self.assertEqual(self.compositor.clients[1]["workspace"]["name"], "set:school:3")

    def test_move_back_without_previous_set_does_not_move_windows(self):
        with self.assertRaisesRegex(RuntimeError, "No previous set"):
            ws.mutate("move-back")
        self.assertEqual(self.compositor.calls, [])

    def test_move_back_rejects_missing_shared_and_pinned_windows(self):
        ws.mutate("switch", "School")
        workspace = copy.deepcopy(self.compositor.monitors[0]["activeWorkspace"])
        for properties, message in (({}, "Focus a window"),
                                    ({"address": "0xtest", "workspace": {"name": "10"}}, "workspace 1–9"),
                                    ({"address": "0xtest", "workspace": {"name": "special:scratch"}}, "workspace 1–9"),
                                    ({"address": "0xtest", "workspace": workspace, "pinned": True}, "Unpin")):
            with self.subTest(properties=properties):
                self.compositor.clients = [properties] if properties else []
                self.compositor.active = properties.get("address")
                self.compositor.calls.clear()
                with self.assertRaisesRegex(RuntimeError, message):
                    ws.mutate("move-back")
                self.assertEqual(self.compositor.calls, [])

    def test_failed_move_back_preserves_state_and_windows(self):
        ws.mutate("switch", "School")
        ws.mutate("back")
        before = ws.read_state()
        clients = copy.deepcopy(self.compositor.clients)
        self.compositor.fail_action = "movetoworkspacesilent"
        with self.assertRaisesRegex(RuntimeError, "injected failure"):
            ws.mutate("move-back")
        self.assertEqual(ws.read_state(), before)
        self.assertEqual(self.compositor.clients, clients)

    def test_move_workspace_back_uses_last_focused_destination_without_a_menu(self):
        self.compositor.monitors[0]["focused"] = False
        self.compositor.monitors.append({"name": "DP-1", "focused": True,
                                         "activeWorkspace": {"id": 2, "name": "2"}})
        self.compositor.active = "0xschool"
        ws.mutate("switch", "School")
        source = copy.deepcopy(self.compositor.monitors[1]["activeWorkspace"])
        for address in ("0xfirst", "0xsecond"):
            self.compositor.clients.append({"address": address, "workspace": source.copy()})
        before = ws.read_state()
        monitors = copy.deepcopy(self.compositor.monitors)
        with patch.object(ws, "choose") as choose:
            ws.mutate("move-workspace-back")
        choose.assert_not_called()
        for client in self.compositor.clients[-2:]:
            self.assertEqual(client["workspace"], {"id": 2, "name": "set:current:2"})
        self.assertEqual(self.compositor.monitors, monitors)
        self.assertEqual(ws.read_state(), before)
        ws.mutate("back")
        self.assertEqual(self.compositor.monitors[1]["activeWorkspace"]["name"], "2")
        self.assertTrue(self.compositor.monitors[1]["focused"])
        self.assertEqual([c["workspace"]["name"] for c in self.compositor.clients[-2:]], ["2", "2"])

    def test_move_workspace_back_falls_back_to_source_slot_without_saved_focus(self):
        ws.mutate("switch", "School")
        ws.mutate("back")
        state = ws.read_state()
        state["sets"]["school"].pop("focused")
        ws.save(state)
        ws.mutate("move-workspace-back")
        self.assertEqual(self.compositor.clients[1]["workspace"]["name"], "set:school:3")

    def test_move_workspace_back_without_previous_set_does_not_move_windows(self):
        with self.assertRaisesRegex(RuntimeError, "No previous set"):
            ws.mutate("move-workspace-back")
        self.assertEqual(self.compositor.calls, [])
        self.assertNotIn("pending_move", ws.read_state())

    def test_move_workspace_merges_all_members_without_touching_other_workspaces(self):
        before = copy.deepcopy(ws.load())
        source = {"id": 3, "name": "3"}
        self.compositor.clients.extend([
            {"address": "0xhidden", "workspace": source.copy(), "hidden": True},
            {"address": "0xpinned", "workspace": source.copy(), "pinned": True},
            {"address": "0xunmapped", "workspace": source.copy(), "mapped": False},
            {"address": "0xdestination", "workspace": {"id": -500, "name": "set:school:5"}},
        ])
        self.compositor.workspaces.append({"id": -500, "name": "set:school:5", "monitor": "eDP-1"})
        monitors = copy.deepcopy(self.compositor.monitors)
        ws.mutate("move-workspace", "sChOoL", "5")
        clients = {c["address"]: c["workspace"] for c in self.compositor.clients}
        for address in ("0xcurrent", "0xhidden", "0xdestination"):
            self.assertEqual(clients[address], {"id": -500, "name": "set:school:5"})
        self.assertEqual(clients["0xschool"], {"id": 2, "name": "2"})
        for address in ("0xpinned", "0xunmapped"):
            self.assertEqual(clients[address], source)
        self.assertEqual(self.compositor.monitors, monitors)
        self.assertEqual(ws.read_state(), before)
        ws.mutate("switch", "School")
        self.assertEqual(self.compositor.clients[1]["workspace"]["name"], "5")
        self.assertEqual(self.compositor.clients[2]["workspace"]["name"], "5")

    def test_move_workspace_failure_returns_already_moved_windows(self):
        before = copy.deepcopy(ws.load())
        self.compositor.clients.append({"address": "0xsecond", "workspace": {"id": 3, "name": "3"}})
        clients = copy.deepcopy(self.compositor.clients)
        original = self.compositor.dispatch
        count = 0

        def fail_second_move(action, arg):
            nonlocal count
            if action == "movetoworkspacesilent":
                count += 1
                if count == 2:
                    raise RuntimeError("injected second move failure")
            original(action, arg)

        with patch.object(ws, "dispatch", fail_second_move):
            with self.assertRaisesRegex(RuntimeError, "second move failure"):
                ws.mutate("move-workspace", "School", "5")
        self.assertEqual(self.compositor.clients, clients)
        self.assertEqual(ws.read_state(), before)

    def test_interrupted_workspace_move_recovers_on_next_command(self):
        before = copy.deepcopy(ws.load())
        clients = copy.deepcopy(self.compositor.clients)
        original = self.compositor.dispatch

        def interrupt(action, arg):
            original(action, arg)
            if action == "movetoworkspacesilent":
                raise KeyboardInterrupt()

        with patch.object(ws, "dispatch", interrupt):
            with self.assertRaises(KeyboardInterrupt):
                ws.mutate("move-workspace", "School", "5")
        self.assertIn("pending_move", ws.read_state())
        # A window closed before recovery should not prevent the others returning.
        state = ws.read_state()
        state["pending_move"]["addresses"].append("0xclosed")
        ws.save(state)
        self.assertEqual(ws.load(), before)
        self.assertEqual(self.compositor.clients, clients)

    def test_workspace_move_rejects_invalid_destinations_and_shared_sources(self):
        ws.load()
        for target, slot, message in (("Current", "5", "different destination"),
                                       ("School", "10", "1–9"),
                                       ("Missing", "5", "No workspace set")):
            with self.subTest(target=target, slot=slot):
                with self.assertRaisesRegex(RuntimeError, message):
                    ws.mutate("move-workspace", target, slot)
        for workspace in ("10", "special:scratch"):
            self.compositor.monitors[0]["activeWorkspace"]["name"] = workspace
            with self.assertRaisesRegex(RuntimeError, "Focus workspace 1–9"):
                ws.mutate("move-workspace", "School", "5")
        self.compositor.monitors[0]["activeWorkspace"]["name"] = "3"
        self.compositor.monitors[0]["specialWorkspace"] = {"id": -99}
        with self.assertRaisesRegex(RuntimeError, "Focus workspace 1–9"):
            ws.mutate("move-workspace", "School", "5")
        self.assertEqual(self.compositor.calls, [])
        self.assertNotIn("pending_move", ws.read_state())

    def test_empty_workspace_move_does_not_start_transaction(self):
        ws.load()
        self.compositor.clients = []
        with self.assertRaisesRegex(RuntimeError, "no windows"):
            ws.mutate("move-workspace", "School", "5")
        self.assertEqual(self.compositor.calls, [])
        self.assertNotIn("pending_move", ws.read_state())

    def test_workspace_move_menu_uses_explicit_set_and_slot(self):
        with patch.object(ws, "choose", side_effect=["School", "Workspace 5 · 0 windows"]) as choose:
            ws.move_workspace_menu()
        self.assertEqual(choose.call_count, 2)
        self.assertEqual(self.compositor.clients[1]["workspace"]["name"], "set:school:5")
        self.assertEqual(self.compositor.monitors[0]["activeWorkspace"]["name"], "3")
        self.assertEqual(ws.read_state()["current"], "current")

    def test_workspace_move_menu_prioritizes_previous_set_and_shows_destination_count(self):
        ws.mutate("switch", "Fun")
        ws.mutate("switch", "School")
        self.compositor.clients.append({"address": "0xfun", "workspace": {"id": -200, "name": "set:fun:5"}})
        with patch.object(ws, "choose", side_effect=["Fun", None]) as choose:
            ws.move_workspace_menu()
        self.assertEqual(choose.call_args_list[0].args[1][0], "Fun")
        self.assertNotIn("School", choose.call_args_list[0].args[1])
        self.assertIn("Workspace 5 · 1 window", choose.call_args_list[1].args[1])

    def test_workspace_move_menu_cancellation_does_not_move_anything(self):
        before = copy.deepcopy(self.compositor.clients)
        for answers in ([None], ["School", None]):
            with self.subTest(answers=answers), patch.object(ws, "choose", side_effect=answers):
                ws.move_workspace_menu()
            self.assertEqual(self.compositor.clients, before)
            self.assertEqual(self.compositor.calls, [])

    def test_workspace_move_menu_rejects_a_set_change_while_choosing(self):
        def choose(prompt, rows):
            if prompt.startswith("Move workspace"):
                ws.mutate("switch", "Fun")
                return "School"
            return "Workspace 5 · 0 windows"

        with patch.object(ws, "choose", choose):
            with self.assertRaisesRegex(RuntimeError, "source workspace changed"):
                ws.move_workspace_menu()
        self.assertFalse(any(action == "movetoworkspacesilent" for action, _ in self.compositor.calls))

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
