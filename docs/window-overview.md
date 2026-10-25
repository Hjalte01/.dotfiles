# Window overview

**Super+Tab** opens one fullscreen overview on the monitor you are using.
**Workspaces** is the default view: one rounded panel per workspace, with windows in their
actual positions inside that workspace. The left terminal stays on the left,
regardless of which terminal was focused most recently. Windows from all monitors,
inactive workspaces in the current workspace set, fullscreen windows and hidden
grouped tabs are included. Parked sets are hidden; **Super+E** switches sets.

The overview follows the active desktop palette, with 10px rounded app cards,
rounded captures, subtle shadows, and an accent border and number badge for the
selected window. Workspace panels keep screen-like proportions rather than
stretching into empty boxes. Their headings show window counts, source monitors,
and the current workspace. The view switch, search field, and keyboard hints use
the same rounded styling. Reading at 100% preserves the original capture pixels.

Window numbers follow workspace order, then top-to-bottom / left-to-right position.
The large **[1]** label is the key to press; the smaller **2.1** means the first
window in workspace 2. Focus changes do not reorder them. Searching and switching
view modes preserve the numbers. Closing, opening or moving windows can change
numbering. Overlapping/fullscreen/grouped windows share their original region as
separate previews, so covered windows remain visible and selectable.

Click a window or press its large number to bring its entire workspace to the
monitor where the overview opened, then focus that window. If the workspace is
visible on another monitor, the visible workspaces swap. The **Focus here** label
shows the destination; workspace headings show the source monitor.

- **Type** to search apps, titles, workspace names and window states.
- **Enter** focuses the highlighted window; arrows move the highlight spatially.
- **Tab** switches between workspace and individual-window views in the same app.
- Click a **workspace heading** to expand it. **All workspaces** returns to the
  overview. This preserves the workspace's window positions at a larger scale.
- **Space** or **Read** opens a reading view at **100%**: one captured pixel per
  screen pixel, without filtering. Drag or scroll to pan; **Fit / Ctrl+0** shows
  the whole window. **100% / Ctrl+1** returns to original pixels. Left/right
  browses windows, **Enter** focuses, and **Space / Escape** returns to the grid.
  **Ctrl+Space** also opens reading while searching; ordinary spaces still work
  in a search phrase.
- **1–9** select the corresponding large window number. **0** selects 10. For
  more windows, type the full number; ambiguous prefixes wait briefly, or can be
  confirmed with **Enter**. **Alt+number** selects while searching.
- **Ctrl+F** or **/** enables numbers in search terms. **Ctrl+U** clears search.
- **Escape** returns from reading, clears a search, leaves an expanded workspace,
  or closes the overview, in that order.

The app is written entirely in Rust: Hyprland IPC, native Wayland window capture,
layout, search, input and rendering. There is no Python, JavaScript, QML or Qt
runtime. `pkgs/window-overview.nix` builds a pinned Cargo package, installed by the
desktop Home Manager module and kept ready by `window-overview.service`.
Other desktop features may still use Quickshell independently.

Captures are full resolution. Thumbnails use SIMD Lanczos downscaling, and labels
are rendered separately at the output resolution. The reading view copies source
pixels directly at 100%. Text necessarily becomes smaller when several complete
workspaces fit on one screen; expand a workspace or use Read for original-size
text. Captures refresh once a second while visible, scaled images and glyphs are
cached, unchanged captures reuse their cache, and the daemon sleeps while closed.
Browser/editor tabs internal to an app remain part of that app's window.

Diagnostics:

```sh
window-overview --list             # Fresh Hyprland snapshot as JSON
window-overview state              # UI state, capture sizes and render time
window-overview open
window-overview inspect 1          # Native-pixel reading view for window 1
window-overview dump /tmp/overview.png
window-overview hide
systemctl --user status window-overview.service
```

Rust tests cover spatial coordinates (including negative monitor origins), stable
numbering when filtering, overlapping windows, rotation/scale and pixel-exact
native cropping. The Nix package runs them during its build.
