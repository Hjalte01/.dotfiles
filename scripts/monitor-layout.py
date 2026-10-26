#!/usr/bin/env python3
"""Arrange active Hyprland monitors, preview, and persist confirmed layouts."""

from __future__ import annotations

import argparse
import copy
import curses
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import time


LAYOUT = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "hypr/monitor-layout.conf"


def hyprctl(*args):
    result = subprocess.run(["hyprctl", *args], capture_output=True, text=True, timeout=8)
    # Monitor JSON can legitimately contain a CONFIGERROR scanout-block reason.
    # Only textual command responses should be inspected for Hyprland errors.
    if result.returncode or ("-j" not in args and "error" in result.stdout.lower()):
        raise RuntimeError((result.stderr or result.stdout).strip() or "Hyprland command failed")
    return result.stdout


def discover():
    # The idle output is virtual; mirrored outputs do not have independent edges.
    return [m for m in json.loads(hyprctl("monitors", "-j"))
            if m["name"] != "idle" and m.get("mirrorOf", "none") in ("none", "", None)]


def size(m):
    w, h = m["width"], m["height"]
    if m.get("transform", 0) % 2:
        w, h = h, w
    return round(w / m["scale"]), round(h / m["scale"])


def edges(m):
    w, h = size(m)
    return m["x"], m["y"], m["x"] + w, m["y"] + h


def overlap(a, b):
    ax, ay, ar, ab = edges(a)
    bx, by, br, bb = edges(b)
    return min(ar, br) > max(ax, bx) and min(ab, bb) > max(ay, by)


def touching(a, b):
    ax, ay, ar, ab = edges(a)
    bx, by, br, bb = edges(b)
    return ((ar == bx or br == ax) and min(ab, bb) > max(ay, by)
            or (ab == by or bb == ay) and min(ar, br) > max(ax, bx))


def validate(monitors):
    for i, a in enumerate(monitors):
        for b in monitors[i + 1:]:
            if overlap(a, b):
                return f"{a['name']} overlaps {b['name']}. Move it to a free edge."
    reached = {0}
    while True:
        adjacent = {j for i in reached for j, m in enumerate(monitors)
                    if touching(monitors[i], m)}
        added = adjacent - reached
        if not added:
            break
        reached.update(added)
    if len(reached) != len(monitors):
        return "Screens must share an edge so the pointer can cross. Press S to snap."
    return ""


def place(m, anchor, side):
    x, y, right, bottom = edges(anchor)
    w, h = size(m)
    m["x"], m["y"] = {
        "left": (x - w, y), "right": (right, y),
        "up": (x, y - h), "down": (x, bottom),
    }[side]


def snap(m, monitors):
    """Attach the selected rectangle to its nearest non-overlapping edge."""
    w, h = size(m)
    candidates = []
    for other in monitors:
        if other is m:
            continue
        x, y, right, bottom = edges(other)
        for px in (x - w, right):
            candidates.append((px, min(max(m["y"], y - h + 1), bottom - 1)))
        for py in (y - h, bottom):
            candidates.append((min(max(m["x"], x - w + 1), right - 1), py))
    candidates.sort(key=lambda p: math.hypot(p[0] - m["x"], p[1] - m["y"]))
    for x, y in candidates:
        candidate = dict(m, x=x, y=y)
        if not any(overlap(candidate, other) for other in monitors if other is not m):
            m.update(x=x, y=y)
            return


def rule(m, *, preferred=False):
    name = m["name"]
    if any(c in name for c in ",;\n\r"):
        raise ValueError("Invalid monitor connector name")
    mode = "preferred" if preferred else f"{m['width']}x{m['height']}@{m['refreshRate']:.5f}"
    return (f"{name}, {mode}, "
            f"{m['x']}x{m['y']}, {m['scale']:g}, transform, {m.get('transform', 0)}")


def apply(monitors):
    current = discover()
    if {m["name"] for m in current} != {m["name"] for m in monitors}:
        raise RuntimeError("Connected screens changed. Press R to refresh before applying.")
    apply_rules(monitors, current)
    for _ in range(15):
        actual = {m["name"]: m for m in discover()}
        if all(m["name"] in actual and
               (actual[m["name"]]["x"], actual[m["name"]]["y"]) == (m["x"], m["y"])
               for m in monitors):
            return
        time.sleep(0.1)
    raise RuntimeError("Hyprland did not accept the requested positions.")


def apply_rules(monitors, current):
    # Park screens beyond both layouts first, avoiding intermediate overlaps when
    # exchanging sides. A single IPC batch completes before the next frame.
    park_x = max(edges(m)[2] for m in monitors + current) + 10000
    commands = []
    for m in monitors:
        parked = dict(m, x=park_x, y=0)
        commands.append("keyword monitor " + rule(parked))
        park_x += size(m)[0] + 100
    commands.extend("keyword monitor " + rule(m) for m in monitors)
    hyprctl("--batch", "; ".join(commands))


def write_layout(contents):
    LAYOUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = LAYOUT.with_suffix(".tmp")
    temporary.write_text(contents)
    temporary.replace(LAYOUT)


def save(monitors):
    # Connectors can be reused by different screens. Persist geometry without
    # forcing the previous screen's resolution or refresh rate on the next one.
    write_layout("# Saved by monitor-layout. Edit with Super+T, then P.\n"
                 + "".join("monitor = " + rule(m, preferred=True) + "\n" for m in monitors))


def migrate_saved_modes():
    if not LAYOUT.exists():
        return
    contents = LAYOUT.read_text()
    if not contents.startswith("# Saved by monitor-layout."):
        return
    updated = re.sub(r"(^[ \t]*monitor[ \t]*=[ \t]*[^,\n]+,[ \t]*)"
                     r"\d+x\d+(?:@[\d.]+)?(?=[ \t]*,)",
                     r"\g<1>preferred", contents, flags=re.MULTILINE)
    if updated != contents:
        write_layout(updated)


class Editor:
    def __init__(self, screen):
        self.screen = screen
        self.monitors = discover()
        if not self.monitors:
            raise RuntimeError("No active physical screens. Choose an extended display mode first.")
        self.original = copy.deepcopy(self.monitors)
        self.selected = next((i for i, m in enumerate(self.monitors) if m["name"] != "eDP-1"), 0)
        self.anchor = next((i for i, m in enumerate(self.monitors) if i != self.selected), 0)
        self.message = "Arrange screens to match your desk. Nothing changes until you press Enter."
        self.deadline = None
        self.drag = None
        self.boxes = []
        self.view = None

    def text(self, y, x, value, attr=0):
        rows, cols = self.screen.getmaxyx()
        if 0 <= y < rows and 0 <= x < cols - 1:
            try:
                self.screen.addnstr(y, x, value, cols - x - 1, attr)
            except curses.error:
                pass

    def draw(self):
        self.screen.erase()
        rows, cols = self.screen.getmaxyx()
        self.text(0, 2, "MONITOR LAYOUT", curses.A_BOLD)
        self.text(1, 2, "Shared edges are where your mouse crosses between screens.")
        if rows < 20 or cols < 66:
            self.text(3, 1, "Enlarge this terminal to at least 66 columns x 20 rows.")
            self.screen.refresh()
            return
        top, height = 4, rows - 13
        left = min(m["x"] for m in self.monitors)
        upper = min(m["y"] for m in self.monitors)
        right = max(edges(m)[2] for m in self.monitors)
        bottom = max(edges(m)[3] for m in self.monitors)
        if self.drag is None:
            # Terminal cells are approximately twice as tall as they are wide.
            factor = min((cols - 8) / max(1, right - left),
                         (height - 2) * 2 / max(1, bottom - upper)) * 0.85
            self.view = (left, upper, factor,
                         4 + int(((cols - 8) - (right - left) * factor) / 2), top + 1)
        left, upper, factor, ox, oy = self.view
        self.boxes = []
        for i, m in enumerate(self.monitors):
            w, h = size(m)
            x = ox + round((m["x"] - left) * factor)
            y = oy + round((m["y"] - upper) * factor / 2)
            bw, bh = max(4, round(w * factor)), max(3, round(h * factor / 2))
            self.boxes.append((x, y, bw, bh))
            attr = curses.color_pair(1) | curses.A_BOLD if i == self.selected else curses.A_DIM
            self.text(y, max(0, x), "+" + "-" * (bw - 1) + "+", attr)
            self.text(y + bh, max(0, x), "+" + "-" * (bw - 1) + "+", attr)
            for line in range(y + 1, y + bh):
                self.text(line, x, "|", attr)
                self.text(line, x + bw, "|", attr)
            self.text(y + 1, max(0, x + 2), f"{i + 1}: {m['name']}"[:bw - 3], attr)
            if bh > 3:
                self.text(y + 2, max(0, x + 2), f"{w} x {h}"[:bw - 3], attr)
        m = self.monitors[self.selected]
        anchor = self.monitors[self.anchor]
        self.text(rows - 8, 2, f"Selected: {m['name']} ({m.get('model', '')})  at {m['x']}, {m['y']}", curses.A_BOLD)
        self.text(rows - 7, 2, f"Reference: {anchor['name']}   |   Arrows place selected screen beside reference")
        if self.deadline:
            status = f"KEEP THIS LAYOUT? Enter/Y keeps it. Esc reverts. Reverting in {max(0, math.ceil(self.deadline - time.monotonic()))}s"
        else:
            status = validate(self.monitors) or self.message
        self.text(rows - 5, 2, status, curses.A_BOLD)
        self.text(rows - 4, 2, "1-9: select screen   Tab/Shift+Tab: next/previous screen")
        self.text(rows - 3, 2, "A: reference   Arrows: place   H/J/K/L: nudge 20px")
        self.text(rows - 2, 2, "Drag: move + snap   S: snap   R: refresh   Enter: preview/save   Q: quit")
        self.screen.refresh()

    def revert(self):
        # Restore remaining screens even if one was unplugged during preview.
        active = {m["name"] for m in discover()}
        remaining = [m for m in self.original if m["name"] in active]
        if remaining:
            apply_rules(remaining, discover())
        self.deadline = None
        self.monitors = copy.deepcopy(self.original)
        self.message = "Previous layout restored."

    def mouse(self):
        _, x, y, _, state = curses.getmouse()
        if state & (curses.BUTTON1_PRESSED | curses.BUTTON1_CLICKED):
            for i, (bx, by, bw, bh) in reversed(list(enumerate(self.boxes))):
                if bx <= x <= bx + bw and by <= y <= by + bh:
                    self.selected = i
                    if self.anchor == i:
                        self.anchor = (i + 1) % len(self.monitors)
                    m = self.monitors[i]
                    self.drag = (x, y, m["x"], m["y"])
                    break
        if self.drag:
            sx, sy, mx, my = self.drag
            factor = self.view[2]
            self.monitors[self.selected].update(x=mx + round((x - sx) / factor),
                                                y=my + round((y - sy) * 2 / factor))
            if state & (curses.BUTTON1_RELEASED | curses.BUTTON1_CLICKED):
                snap(self.monitors[self.selected], self.monitors)
                self.drag = None

    def run(self):
        curses.curs_set(0)
        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
        curses.mouseinterval(0)
        self.screen.timeout(100)
        directions = {curses.KEY_LEFT: "left", curses.KEY_RIGHT: "right",
                      curses.KEY_UP: "up", curses.KEY_DOWN: "down"}
        try:
            while True:
                self.draw()
                key = self.screen.getch()
                if self.deadline:
                    if key in (10, 13, ord("y"), ord("Y")):
                        save(self.monitors)
                        self.deadline = None
                        self.original = copy.deepcopy(self.monitors)
                        self.message = "Layout saved. It will also be used after login and desktop reload."
                    elif key in (27, ord("q"), ord("Q")) or time.monotonic() >= self.deadline:
                        self.revert()
                    continue
                if key in (ord("q"), ord("Q"), 27):
                    return
                if ord("1") <= key <= ord("9"):
                    index = key - ord("1")
                    if index < len(self.monitors):
                        self.selected = index
                        if self.anchor == self.selected:
                            self.anchor = (self.selected + 1) % len(self.monitors)
                elif key in (9, curses.KEY_BTAB):
                    self.selected = (self.selected + (-1 if key == curses.KEY_BTAB else 1)) % len(self.monitors)
                    if self.anchor == self.selected:
                        self.anchor = (self.selected + 1) % len(self.monitors)
                elif key in (ord("a"), ord("A")) and len(self.monitors) > 1:
                    self.anchor = (self.anchor + 1) % len(self.monitors)
                    if self.anchor == self.selected:
                        self.anchor = (self.anchor + 1) % len(self.monitors)
                elif key in directions and len(self.monitors) > 1:
                    place(self.monitors[self.selected], self.monitors[self.anchor], directions[key])
                elif key in map(ord, "hjklHJKL"):
                    dx, dy = {"h": (-20, 0), "j": (0, 20), "k": (0, -20), "l": (20, 0)}[chr(key).lower()]
                    m = self.monitors[self.selected]
                    m["x"] += dx
                    m["y"] += dy
                elif key in (ord("s"), ord("S")):
                    snap(self.monitors[self.selected], self.monitors)
                elif key in (ord("r"), ord("R")):
                    self.__init__(self.screen)
                elif key == curses.KEY_MOUSE:
                    self.mouse()
                elif key in (10, 13) and not validate(self.monitors):
                    self.original = discover()
                    self.deadline = time.monotonic() + 15
                    apply(self.monitors)
        finally:
            if self.deadline:
                self.revert()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--place", nargs=3, metavar=("OUTPUT", "SIDE", "REFERENCE"),
                        help="place an output left/right/up/down of a reference; requires --save")
    parser.add_argument("--save", action="store_true", help="save a layout applied with --place")
    parser.add_argument("--migrate-saved-layout", action="store_true",
                        help="update generated saved layouts to use each screen's preferred mode")
    args = parser.parse_args()
    if args.migrate_saved_layout and (args.place or args.save):
        parser.error("--migrate-saved-layout cannot be combined with --place or --save")
    # Make terminal closure and interruption unwind the preview's finally block.
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGHUP, interrupted)
    try:
        if args.migrate_saved_layout:
            migrate_saved_modes()
            return
        if args.place:
            output, side, reference = args.place
            monitors = discover()
            by_name = {m["name"]: m for m in monitors}
            if not args.save or side not in ("left", "right", "up", "down") or output == reference:
                parser.error("use --place OUTPUT left|right|up|down REFERENCE --save")
            if output not in by_name or reference not in by_name:
                parser.error("both outputs must be active, independent physical screens")
            place(by_name[output], by_name[reference], side)
            if problem := validate(monitors):
                parser.error(problem)
            original = discover()
            try:
                apply(monitors)
                save(monitors)
            except BaseException:
                apply(original)
                raise
            print(f"Saved {output} {side} of {reference}.")
        else:
            curses.wrapper(lambda screen: Editor(screen).run())
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"monitor-layout: {error}\n")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
