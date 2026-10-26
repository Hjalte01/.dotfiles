#!/usr/bin/env python3
"""Desktop app launcher with inline priority controls and shortcut help."""

import argparse
from html import escape
import json
import os
from pathlib import Path
import subprocess
import tempfile


CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "app-launcher/priorities.json"
STATE = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "app-launcher/history.json"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "rofi3.druncache"
DEFAULT_LOW = {
    "net.lutris.Lutris.desktop", "net.lutris.Lutris1.desktop",
    "roblox.desktop", "org.vinegarhq.Sober.desktop", "org.vinegarhq.Vinegar.desktop",
    "steam.desktop", "org.prismlauncher.PrismLauncher.desktop",
    "geforce-now.desktop", "com.nvidia.geforcenow.desktop",
    "ubisoft-connect.desktop", "far-cry-3.desktop",
    "Counter-Strike Source.desktop", "It Takes Two.desktop",
    "wine-Programs-EA-EA.desktop", "wine-Programs-EA-App Recovery.desktop",
    "wine-Programs-EA-EA app Updater.desktop", "wine-Programs-EA-EA Error Reporter.desktop",
}


def read_json(path):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
    temporary.replace(path)


def is_low(app_id, overrides):
    return overrides.get(app_id, "low" if app_id in DEFAULT_LOW else "normal") == "low"


def load_history():
    if STATE.exists():
        raw = read_json(STATE)
        return {key: value for key, value in raw.items()
                if isinstance(value, int) and value >= 0}
    # Preserve existing drun frequency ordering when switching to this launcher.
    history = {}
    try:
        for line in CACHE.read_text().splitlines():
            count, _, app_id = line.partition(" ")
            if count.isdigit() and app_id:
                history[app_id] = int(count)
    except OSError:
        pass
    return history


def discover():
    from gi.repository import Gio

    apps = []
    for info in Gio.AppInfo.get_all():
        if not info.should_show() or not info.get_id():
            continue
        icon = info.get_icon()
        apps.append({
            "id": info.get_id(), "name": info.get_display_name(),
            "icon": icon.to_string() if icon else "application-x-executable",
            "meta": " ".join(filter(None, [
                info.get_generic_name(), info.get_description(),
                info.get_executable(), info.get_categories(),
                " ".join(info.get_keywords() or []),
            ])),
            "info": info,
        })
    return apps


def ordered(apps, overrides, history):
    return sorted(apps, key=lambda app: (
        is_low(app["id"], overrides), -history.get(app["id"], 0),
        app["name"].casefold(), app["id"],
    ))


def clean(value):
    # Desktop strings must not inject extra rows or Rofi metadata fields.
    return " ".join(str(value).replace("\0", " ").replace("\x1f", " ").splitlines())


def rows(apps, overrides=None):
    overrides = overrides or {}
    output = []
    for app in apps:
        name = escape(clean(app["name"]))
        dot = '  <span foreground="#888888" size="small">·</span>' if is_low(app["id"], overrides) else ""
        # Keep search terms in the input string: Rofi 2.0's initial filter
        # skips metadata. Display only the escaped app name and priority dot.
        search = escape(f'{clean(app["name"])} {clean(app["meta"])}')
        output.append(f'{search}\0display\x1f{name}{dot}\x1ficon\x1f{clean(app["icon"])}\n')
    return "".join(output)


def menu_command(fullscreen=False, query="", selected=0, help_open=False, error=""):
    command = [str(Path.home() / ".local/bin/rofi-menu")]
    if fullscreen:
        command.append("--fullscreen")
    message = '<span alpha="65%">Ctrl+?</span>'
    if help_open:
        message += ("\nEnter: open app · ↑/↓: select · Esc: close"
                    "\nCtrl+P: toggle selected app between normal and lower priority"
                    "\nGrey dot: lower priority · Ctrl+?: hide shortcuts")
    if error:
        message += "\n" + escape(error)
    return command + [
        # Allow the help binding even when the filter has no matches; launch()
        # only opens a valid desktop row, never arbitrary typed input.
        "-dmenu", "-i", "-no-sort", "-show-icons", "-markup-rows", "-format", "i\nf",
        "-p", "Apps", "-kb-row-up", "Up", "-kb-custom-1", "Control+p", "-kb-toggle-sort", "",
        "-kb-custom-2", "Control+question,Control+Shift+question,Control+slash",
        "-filter", query, "-selected-row", str(selected), "-mesg", message,
    ]


def launch_app(info):
    if info.get_boolean("Terminal"):
        from gi.repository import Gio, GLib

        # Keep desktop-file field codes, working directory and quoting intact,
        # while using the configured desktop terminal rather than Gio's fallback.
        keyfile = GLib.KeyFile()
        keyfile.load_from_file(info.get_filename(), GLib.KeyFileFlags.NONE)
        command = keyfile.get_string("Desktop Entry", "Exec")
        keyfile.set_string("Desktop Entry", "Exec", f"ghostty -e {command}")
        keyfile.set_boolean("Desktop Entry", "Terminal", False)
        keyfile.set_boolean("Desktop Entry", "DBusActivatable", False)
        info = Gio.DesktopAppInfo.new_from_keyfile(keyfile)
    info.launch([], None)


def launch(fullscreen=False):
    installed = discover()
    query, selected_id, help_open, error = "", None, False, ""
    while True:
        overrides = read_json(CONFIG)
        apps = ordered(installed, overrides, load_history())
        selected = next((i for i, app in enumerate(apps) if app["id"] == selected_id), 0)
        result = subprocess.run(
            menu_command(fullscreen, query, selected, help_open, error),
            input=rows(apps, overrides), text=True, capture_output=True,
        )
        if result.returncode not in (0, 10, 11):
            return
        index_text, _, query = result.stdout.rstrip("\n").partition("\n")
        try:
            index = int(index_text)
            app = apps[index] if 0 <= index < len(apps) else None
        except ValueError:
            app = None
        selected_id = app["id"] if app else None
        error = ""
        if result.returncode == 11:
            help_open = not help_open
            continue
        if app is None:
            if result.returncode == 0:
                return
            continue
        if result.returncode == 10:
            overrides[app["id"]] = "normal" if is_low(app["id"], overrides) else "low"
            try:
                write_json(CONFIG, overrides)
            except OSError as exception:
                error = f"Could not save priority: {exception}"
            continue
        try:
            launch_app(app["info"])
        except Exception as exception:
            subprocess.run(["rofi", "-e", f'Could not launch {app["name"]}: {exception}'])
            return
        history = load_history()
        history[app["id"]] = history.get(app["id"], 0) + 1
        write_json(STATE, history)
        return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=["launch", "list"], default="launch")
    parser.add_argument("--fullscreen", action="store_true")
    args = parser.parse_args()
    if args.command == "list":
        overrides = read_json(CONFIG)
        for app in ordered(discover(), overrides, load_history()):
            print(f'{"lower" if is_low(app["id"], overrides) else "normal"}\t{app["name"]}\t{app["id"]}')
    else:
        launch(args.fullscreen)


if __name__ == "__main__":
    main()
