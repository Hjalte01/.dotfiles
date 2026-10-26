# Glance

Hold **Super+Q** to show the time, weekday, date, and battery status. Releasing
either key closes it. Press **Escape while holding Super+Q** to pin it; release
the shortcut, then press any key to close it. `glance` also opens a pinned popup.

The popup grabs keyboard shortcuts while visible so Super+Escape pins Glance
instead of opening the desktop key map. Its release handler covers quick taps
that finish before GTK has keyboard focus.

Run the input-state checks without interacting with the desktop:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_glance.py -v
```

## Live test incident, 2026-10-18

At 15:13:51 CEST the desktop session terminated during a temporary shortcut test.
The test's cleanup passed a PID from `hyprctl -j layers` directly to `os.kill`.
Hyprland 0.55.1 can return `-1` for a layer whose client has closed while the
layer is still fading out. `kill(-1, SIGTERM)` signals all processes the caller
can terminate. This is the likely cause of the session-wide shutdown; the
Hyprland launcher then aborted in its signal handler with “Resource deadlock
avoided”. The machine did not reboot.

This cleanup was temporary test code, never part of the installed command.
Do not simulate keyboard input on the live desktop for automated tests. For GUI
tests, use an isolated display and retain the `subprocess.Popen` objects of the
processes started by the test. Clean up those child processes through their
process handles; never use compositor-reported PIDs as kill targets.
