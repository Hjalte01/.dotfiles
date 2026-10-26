#!/usr/bin/env python3
"""Peek at the time, date, and battery; Escape pins a held peek."""

from time import monotonic_ns

STARTED_NS = monotonic_ns()

import argparse
import os
from datetime import datetime
from pathlib import Path


class PopupKeys:
    """Keep the pinning press and held shortcut repeats from dismissing a pin."""

    def __init__(self, hold=False):
        self.pinned = not hold
        self.ignore_until_release = set()

    def press(self, key):
        if not self.pinned:
            if key == "Escape":
                self.pinned = True
                self.ignore_until_release = {"Escape", "q", "Super_L", "Super_R"}
            return False
        return key not in self.ignore_until_release

    def release(self, key):
        self.ignore_until_release.discard(key)
        return not self.pinned and key in {"q", "Super_L", "Super_R"}


def battery_text(supply_dir=Path("/sys/class/power_supply")):
    batteries = []
    for supply in sorted(supply_dir.iterdir()):
        try:
            if (supply / "type").read_text().strip() != "Battery":
                continue
            if (supply / "scope").exists() and (supply / "scope").read_text().strip() == "Device":
                continue
            capacity = int((supply / "capacity").read_text().strip())
            status = (supply / "status").read_text().strip()
        except (OSError, ValueError):
            continue
        batteries.append(f"Battery {capacity}% · {status}")
    return "\n".join(batteries) or "No battery"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hold", action="store_true", help="Show while Super+Q is held; Escape pins")
    parser.add_argument("--release", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    release_file = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "glance-release"
    if args.release:
        release_file.write_text(str(monotonic_ns()))
        return
    keys = PopupKeys(hold=args.hold)

    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import Gdk, GLib, Gtk, GtkLayerShell

    window = Gtk.Window(title="Glance")
    window.set_name("glance")
    window.set_resizable(False)
    GtkLayerShell.init_for_window(window)
    GtkLayerShell.set_namespace(window, "glance")
    GtkLayerShell.set_layer(window, GtkLayerShell.Layer.OVERLAY)
    GtkLayerShell.set_keyboard_mode(window, GtkLayerShell.KeyboardMode.EXCLUSIVE)
    # No edge anchors: layer-shell centers the popup on the selected output.
    GtkLayerShell.set_exclusive_zone(window, 0)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    box.set_border_width(28)
    window.add(box)
    clock = Gtk.Label()
    clock.set_name("clock")
    date = Gtk.Label()
    battery = Gtk.Label()
    battery.set_justify(Gtk.Justification.CENTER)
    box.pack_start(clock, False, False, 0)
    box.pack_start(date, False, False, 0)
    box.pack_start(battery, False, False, 0)
    hint = Gtk.Label()
    hint.set_name("hint")
    box.pack_start(hint, False, False, 4)

    css = Gtk.CssProvider()
    css.load_from_data(b"""
        #glance { background-color: @theme_bg_color; color: @theme_fg_color;
                  border: 2px solid @theme_selected_bg_color; border-radius: 14px; }
        #glance label { font-size: 18px; }
        #glance #clock { font-size: 56px; font-weight: bold; }
        #glance #hint { font-size: 12px; opacity: 0.7; }
    """)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )

    def refresh():
        now = datetime.now()
        clock.set_text(now.strftime("%H:%M"))
        date.set_text(f"{now:%A}, {now.day} {now:%B %Y}")
        battery.set_text(battery_text())
        hint.set_text("Pinned · press any key to close" if keys.pinned else "Hold Super+Q · Esc to pin")
        return GLib.SOURCE_CONTINUE

    def dismiss(*_args):
        Gdk.Display.get_default().get_default_seat().ungrab()
        Gtk.main_quit()
        return True

    def grab_keyboard(_window, _event):
        # Inhibit desktop shortcuts while open, including Super+Escape's key map.
        Gdk.Display.get_default().get_default_seat().grab(
            window.get_window(), Gdk.SeatCapabilities.KEYBOARD, False, None, None, None, None
        )
        if args.hold:
            GLib.timeout_add(50, check_hold)
        return False

    def check_hold():
        if keys.pinned:
            return GLib.SOURCE_REMOVE
        # A quick tap can finish before GTK receives keyboard focus. The release
        # binding records Q's release; the keymap also catches an early Super release.
        try:
            released = int(release_file.read_text()) > STARTED_NS
        except (OSError, ValueError):
            released = False
        modifiers = Gdk.Keymap.get_for_display(Gdk.Display.get_default()).get_modifier_state()
        if released or not modifiers & (Gdk.ModifierType.SUPER_MASK | Gdk.ModifierType.MOD4_MASK):
            dismiss()
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def key_event(_window, event):
        key = Gdk.keyval_name(Gdk.keyval_to_lower(event.keyval))
        close = keys.press(key) if event.type == Gdk.EventType.KEY_PRESS else keys.release(key)
        if close:
            dismiss()
        else:
            refresh()
        return True

    window.connect("key-press-event", key_event)
    window.connect("key-release-event", key_event)
    window.connect("map-event", grab_keyboard)
    window.connect("destroy", dismiss)
    refresh()
    GLib.timeout_add_seconds(1, refresh)
    window.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
