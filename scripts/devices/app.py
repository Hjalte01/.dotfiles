"""Offline-first device comparison and capacity planning in the terminal."""
from __future__ import annotations

import datetime as dt
import math
import re

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, DataTable, Footer, Header, Input, Label, Select, Static

from dotfiles_theme import install as install_theme

from . import core


def sample_label(device: dict) -> str:
    sample = device.get("benchmark")
    if not sample:
        return "not measured"
    if sample.get("suite") != "pbkdf2-sha256-v1" or sample.get("unit") != "derivations/s":
        return "other suite · details"
    return f"{sample['single']:.1f} / {sample['multi']:.1f}"


def snapshot_label(device: dict) -> str:
    """Keep the age visible beside values that can change between observations."""
    stamp = device.get("live_observed_at")
    if not stamp:
        confidence = device.get("confidence", "").lower()
        if "unconfirmed" in confidence or "unverified" in confidence:
            return "partial specs" if device.get("specs", {}).get("cpu") else "unconfirmed"
        return "hardware only" if device.get("observed_at") else "reference"
    try:
        observed = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        age = max(0, (dt.datetime.now(dt.timezone.utc) - observed).total_seconds())
    except (ValueError, TypeError):
        return "cached · unknown age"
    if age < 60:
        return "snapshot <1m"
    if age < 300:
        return f"snapshot {int(age // 60)}m"
    if age < 3600:
        return f"cached {int(age // 60)}m"
    if age < 86400:
        return f"cached {int(age // 3600)}h"
    return f"cached {int(age // 86400)}d"


def number(text: str, name: str, *, integer: bool = False) -> float | int | None:
    """An empty field is unknown; zero is an explicit value."""
    if not text.strip():
        return None
    try:
        result = float(text)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, or leave it empty.") from exc
    if not math.isfinite(result) or result < 0 or (integer and (result < 1 or not result.is_integer())):
        raise ValueError(f"{name} must be a {'positive whole' if integer else 'non-negative'} number.")
    return int(result) if integer else result


class CompareTable(DataTable):
    BINDINGS = [
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
        Binding("h", "cursor_left", show=False),
        Binding("l", "cursor_right", show=False),
    ]


class DeviceForm(ModalScreen[dict | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="dialog"):
            yield Static("Add a device", classes="dialog-title")
            yield Static("Leave unknown specs empty. Linux hosts can be probed after adding.", classes="muted")
            yield Label("ID · unique short name, e.g. work-laptop")
            yield Input(placeholder="work-laptop", id="device-id")
            yield Label("Display name")
            yield Input(placeholder="Work laptop", id="device-name")
            yield Label("Platform")
            yield Select([("Linux", "linux"), ("iPhone / iOS", "ios"),
                          ("iPad / iPadOS", "ipados"), ("Other", "other")],
                         value="linux", allow_blank=False, id="device-kind")
            yield Label("SSH target · existing SSH alias, optional")
            yield Input(placeholder="work-laptop", id="device-ssh")
            yield Label("Local hostname · only for a device you refresh locally")
            yield Input(placeholder="hostname", id="device-hostname")
            yield Label("CPU model · optional")
            yield Input(id="device-cpu")
            yield Label("RAM in GiB · optional")
            yield Input(placeholder="16", id="device-ram")
            yield Label("Logical CPUs / vCPUs · optional")
            yield Input(placeholder="8", id="device-threads")
            yield Static("", id="form-error")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Add device", variant="primary", id="save-device")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#device-id", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        value = lambda field: self.query_one(f"#device-{field}", Input).value.strip()
        try:
            identifier, name = value("id"), value("name")
            if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", identifier):
                raise ValueError("Use lowercase letters, numbers, underscores or hyphens for the ID (up to 64 characters).")
            if not name:
                raise ValueError("Give the device a display name.")
            if identifier in {device["id"] for device in core.load_devices()}:
                raise ValueError("That ID already exists. Choose a new ID.")
            ram = number(value("ram"), "RAM")
            threads = number(value("threads"), "Logical CPUs", integer=True)
            device = {
                "id": identifier, "name": name,
                "kind": self.query_one("#device-kind", Select).value,
                "hostname": value("hostname") or None,
                "ssh": value("ssh") or None,
                "specs": {"cpu": value("cpu") or None,
                          "ram_bytes": int(ram * 2**30) if ram is not None else None,
                          "threads": threads},
                "confidence": "manual", "source": "User-entered inventory",
                "notes": [], "sources": [],
            }
            core.save_device(device)
        except (ValueError, OSError) as exc:
            self.query_one("#form-error", Static).update(Text(str(exc), style="red"))
            return
        self.dismiss(device)


class JobFit(ModalScreen[None]):
    BINDINGS = [Binding("escape", "close", "Close")]

    def __init__(self, devices: list[dict]) -> None:
        super().__init__()
        self.devices = devices

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="dialog"):
            yield Static("Can this job fit?", classes="dialog-title")
            yield Static("Capacity checks use saved observations. Refresh before committing a job.", classes="muted")
            yield Label("RAM needed · GiB")
            yield Input(placeholder="2", id="job-ram")
            yield Label("Logical CPUs / vCPUs needed")
            yield Input(placeholder="2", id="job-cpus")
            yield Label("Additional disk needed · GiB")
            yield Input(placeholder="5", id="job-disk")
            yield Checkbox("Requires NVIDIA CUDA", id="job-cuda")
            yield Label("Required architecture")
            yield Select([("Any architecture", "any"), ("x86_64", "x86_64"),
                          ("aarch64 / ARM64", "aarch64")],
                         value="any", allow_blank=False, id="job-architecture")
            yield Static("", id="job-error")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Check devices", variant="primary", id="check-job")
                yield Button("Close", id="close")
            yield Static("Enter the job's requirements, then check devices.", id="job-results", markup=False)

    def action_close(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "close":
            self.dismiss(None)
            return
        try:
            requirements = {
                "ram_gib": number(self.query_one("#job-ram", Input).value, "RAM") or 0,
                "cpus": number(self.query_one("#job-cpus", Input).value, "CPUs", integer=True) or 0,
                "disk_gib": number(self.query_one("#job-disk", Input).value, "Disk") or 0,
                "cuda": self.query_one("#job-cuda", Checkbox).value,
            }
            architecture = self.query_one("#job-architecture", Select).value
            requirements["architecture"] = architecture if architecture != "any" else None
            results = Text()
            for device in self.devices:
                result = core.assess(device, **requirements)
                style = {"fits": "green", "blocked": "red", "unknown": "yellow", "check": "yellow"}.get(result["status"], "")
                results.append(f"{device['name']}  ·  {result['status'].upper()}\n", style=style)
                results.append("\n".join(f"  {reason}" for reason in result["reasons"]) + "\n\n")
            self.query_one("#job-results", Static).update(results)
            self.query_one("#job-error", Static).update("")
        except ValueError as exc:
            self.query_one("#job-error", Static).update(Text(str(exc), style="red"))


class Help(ModalScreen[None]):
    BINDINGS = [Binding("escape,q,?", "close", "Close")]

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="dialog"):
            yield Static("Device comparer", classes="dialog-title")
            yield Static(
                "↑/↓ or j/k  Select a device\n"
                "←/→ or h/l  Scroll wide tables\n"
                "Tab / Shift+Tab  Move between table and details\n"
                "r  Refresh selected Linux host (local or SSH)\n"
                "Ctrl+r  Reload saved inventory and snapshots\n"
                "a  Add a device\n"
                "f  Check a job's requirements\n"
                "q  Quit\n\n"
                "All sizes are GiB. CPU threads and vCPUs describe capacity; they are not speed scores. "
                "Free RAM and disk are timestamped observations. An old snapshot cannot guarantee current capacity. "
                "iOS and iPadOS devices are listed for comparison and are not ordinary Linux job hosts.\n\n"
                "CPU sample 1 / N shows single-worker / multi-worker PBKDF2-SHA256 derivations per second "
                "(suite: pbkdf2-sha256-v1). Higher is faster for this workload only. "
                "The measurement time and worker count are in device details; samples stay cached until measured again. "
                "Run devices bench ID to measure a configured Linux host.\n\n"
                f"Inventory: {core.inventory_path()}\n\n"
                "Use devices --json for Codex, devices edit for full inventory editing, and devices --help for CLI commands.",
                markup=False,
            )
            yield Button("Close", id="close")

    def action_close(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self) -> None:
        self.dismiss(None)


class DevicesApp(App):
    TITLE = "Devices"
    SUB_TITLE = "Specs · capacity · job fit"
    CSS = """
    Screen { background: $background; }
    #banner { height: 3; padding: 0 2; }
    #comparison { height: 1fr; min-height: 7; margin: 0 1; border: round $primary; }
    #details { height: 1fr; min-height: 6; margin: 0 1; padding: 0 1; border: round $border; }
    #detail-body { height: auto; }
    #status { height: 2; padding: 0 2; color: $text-muted; }
    .dialog { width: 78; max-width: 95%; height: auto; max-height: 92%;
              background: $surface; border: round $primary; padding: 1 2; }
    ModalScreen { align: center middle; background: $background 70%; }
    .dialog-title { text-style: bold; color: $primary; margin-bottom: 1; height: auto; }
    .muted { color: $text-muted; height: auto; margin-bottom: 1; }
    .dialog Label { margin-top: 1; }
    .dialog Input, .dialog Select { width: 100%; }
    .dialog-buttons { height: 3; margin: 1 0; }
    .dialog-buttons Button { margin-right: 1; }
    #form-error, #job-error, #job-results { height: auto; }
    #job-results { margin-top: 1; }
    """
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh host"),
        Binding("ctrl+r", "reload", "Reload"),
        Binding("a", "add", "Add device"),
        Binding("f", "fit", "Job fit"),
        Binding("?", "help", "Help"),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.devices: list[dict] = []
        self.refreshing = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="banner")
        yield CompareTable(id="comparison", cursor_type="row", zebra_stripes=True, fixed_columns=1)
        with VerticalScroll(id="details", can_focus=True):
            yield Static("", id="detail-body", markup=False)
        yield Static("Snapshots stay available offline. Refresh a host before planning a job.", id="status")
        yield Footer()

    def on_mount(self) -> None:
        install_theme(self)
        table = self.query_one("#comparison", DataTable)
        table.border_title = "Compare devices · GiB"
        self.query_one("#details", VerticalScroll).border_title = "Selected device"
        for label, width in [("Device", 25), ("CPU", 34), ("CPU slots", 13), ("CPU sample 1 / N", 20), ("RAM", 9),
                             ("RAM available", 14), ("Disk free / total", 20), ("GPU", 25), ("Observation", 20)]:
            table.add_column(label, width=width, key=label)
        self.action_reload()
        table.focus()
        self.set_interval(30, self.update_age_labels)

    def selected(self) -> dict | None:
        table = self.query_one("#comparison", DataTable)
        if not table.row_count:
            return None
        key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        return next((device for device in self.devices if device["id"] == key), None)

    def action_reload(self) -> None:
        previous = self.selected() if self.devices else None
        try:
            self.devices = core.load_devices()
        except (OSError, ValueError) as exc:
            self.query_one("#status", Static).update(Text(f"Could not load inventory: {exc}", style="red"))
            return
        table = self.query_one("#comparison", DataTable)
        table.clear()
        for device in self.devices:
            specs, live = device.get("specs", {}), device.get("live", {})
            slots = specs.get("threads")
            if slots is not None:
                slots = f"{slots} vCPU" if specs.get("virtualized") else f"{specs.get('cores') or '?'}c / {slots}t"
            table.add_row(
                Text(device["name"]), Text(specs.get("cpu") or "Unknown"), str(slots or "Unknown"),
                sample_label(device), core.gib(specs.get("ram_bytes")), core.gib(live.get("ram_available_bytes")),
                f"{core.gib(live.get('disk_available_bytes'))} / {core.gib(specs.get('disk_bytes'))}",
                Text(specs.get("gpu") or "Unknown"), snapshot_label(device), key=device["id"],
            )
        if previous:
            for index, device in enumerate(self.devices):
                if device["id"] == previous["id"]:
                    table.move_cursor(row=index)
                    break
        linux_count = sum(device.get("kind") == "linux" for device in self.devices)
        banner = Text(f"{len(self.devices)} devices  ·  {linux_count} Linux hosts\n", style="bold")
        banner.append("Compare hardware, inspect available resources, and check where a job can fit.", style="dim")
        self.query_one("#banner", Static).update(banner)
        self.update_details()

    def update_age_labels(self) -> None:
        table = self.query_one("#comparison", DataTable)
        for device in self.devices:
            table.update_cell(device["id"], "Observation", snapshot_label(device))

    def on_data_table_row_highlighted(self) -> None:
        self.update_details()

    def update_details(self) -> None:
        device = self.selected()
        body = self.query_one("#detail-body", Static)
        if not device:
            body.update("No devices yet. Press a to add one.")
            return
        lines = core.detail_lines(device)
        detail = Text(lines[0] + "\n", style="bold")
        detail.append("\n".join(lines[1:]))
        body.update(detail)
        self.query_one("#details", VerticalScroll).scroll_home(animate=False)

    def action_add(self) -> None:
        self.push_screen(DeviceForm(), self.device_added)

    def device_added(self, device: dict | None) -> None:
        if device:
            self.action_reload()
            table = self.query_one("#comparison", DataTable)
            table.move_cursor(row=next(i for i, d in enumerate(self.devices) if d["id"] == device["id"]))
            self.query_one("#status", Static).update(f"Added {device['name']}. Press r to inspect a configured Linux host.")

    def action_fit(self) -> None:
        self.push_screen(JobFit(self.devices))

    def action_help(self) -> None:
        self.push_screen(Help())

    def action_refresh(self) -> None:
        device = self.selected()
        if device is None or self.refreshing:
            return
        self.refreshing = True
        self.query_one("#status", Static).update(f"Reading {device['name']}… SSH has a bounded timeout; saved data stays available.")
        self.refresh_selected(device)

    @work(thread=True, exclusive=True)
    def refresh_selected(self, device: dict) -> None:
        try:
            core.refresh_device(device)
        except Exception as exc:
            self.call_from_thread(self.refresh_finished, device, str(exc))
        else:
            self.call_from_thread(self.refresh_finished, device, None)

    def refresh_finished(self, device: dict, error: str | None) -> None:
        self.refreshing = False
        if error:
            self.query_one("#status", Static).update(Text(f"Refresh failed: {error} · saved snapshot retained.", style="yellow"))
        else:
            self.action_reload()
            self.query_one("#status", Static).update(f"Updated {device['name']}. Available resources are a snapshot of this moment.")
