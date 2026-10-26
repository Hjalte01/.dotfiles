# Window overview

**Super+Tab** opens one fullscreen overview on the monitor you are using.
**Workspaces** is the default view: one rounded panel per workspace, with windows in their
actual positions inside that workspace. The left terminal stays on the left,
regardless of which terminal was focused most recently. Windows from all monitors,
inactive workspaces in the current workspace set, fullscreen windows and hidden
grouped tabs are included. The **Current set / All sets** toggle controls whether
Workspaces and Windows include parked sets; **Ctrl+A** toggles this scope.
The scope is shared between those views, and the chosen view and scope are
remembered while the overview service is running. **Super+E** still switches sets.

The view switch is **Workspaces | Windows**. Empty workspaces are hidden in both
scopes. In Workspaces with All sets enabled, a named outer box groups each set’s
workspaces. Only sets containing matching windows appear. Windows stays a flat,
searchable grid across the selected scope. Headings also show
the monitor; **Saved** marks a parked set’s remembered visible workspace.
Click a workspace heading to expand it; **Escape** backs out.

The overview follows the active desktop palette, with 10px rounded app cards,
rounded captures, subtle shadows, and an accent border and number badge for the
selected window. Workspace panels keep screen-like proportions rather than
stretching into empty boxes. Their headings show window counts, source monitors,
and the current workspace. The view switch, search field, and keyboard hints use
the same rounded styling. Expanded previews at 100% preserve the original capture pixels.

Window numbers follow workspace order, then top-to-bottom / left-to-right position.
The large **[1]** label is the key to press; the smaller **2.1** means the first
window in workspace 2. Focus changes do not reorder them. Searching and switching
view modes preserve the numbers. Closing, opening or moving windows can change
numbering. Overlapping/fullscreen/grouped windows share their original region as
separate previews, so covered windows remain visible and selectable.

Click a window or press its large number to bring its entire workspace to the
monitor where the overview opened, then focus that window. If the workspace is
visible on another monitor, the visible workspaces swap. Selecting a parked
window first switches to its set through the normal workspace-set transaction,
preserving layouts and previous-set history. The **Focus here** label
shows the destination; workspace headings show the source monitor.

- **Type** to search apps, titles, workspace names, set names and window states.
- **Enter** focuses the highlighted window; arrows move the highlight spatially.
- **Tab / Shift+Tab** switch views forward/backward. **Ctrl+Tab / Ctrl+Shift+Tab**
  also work. With two views, either direction selects the other view.
- **Ctrl+A** toggles Current set / All sets in both views.
- **Page Up / Page Down** browse previous/next windows, wrapping at the ends.
  **Home / End** select the first/last result. These work in expanded previews
  too and respect the current search and scope.
- Click a **workspace heading** to expand it. **All workspaces** returns to the
  overview. This preserves the workspace's window positions at a larger scale.
- **Space** or the **expand icon** enlarges the captured preview at **100%**:
  one captured pixel per screen pixel, without filtering. Drag or scroll to pan; **Fit / Ctrl+0** shows
  the whole window. **100% / Ctrl+1** returns to original pixels. Left/right
  browses windows, **Enter** focuses, and **Space / Escape** returns to the grid.
  **Ctrl+Space** also expands previews while searching; ordinary spaces still work
  in a search phrase.
- **1–9** select the corresponding large window number. **0** selects 10. For
  more windows, type the full number; ambiguous prefixes wait briefly, or can be
  confirmed with **Enter**. **Alt+number** selects while searching.
- **Ctrl+F**, **Ctrl+L**, or **/** enters search mode, including numbers in search
  terms. **Ctrl+Backspace** deletes the last word; **Ctrl+U** clears search.
- **Escape** returns from the expanded preview, clears a search, leaves an expanded workspace,
  or closes the overview, in that order. **Alt+Left** also goes back.

The overview UI is written entirely in Rust: Hyprland IPC, native Wayland window
capture, layout, search, input and rendering. Window activation delegates to the
existing `workspace-set` helper so it shares set switching and locking.
`pkgs/window-overview.nix` builds a pinned Cargo package, installed by the
desktop Home Manager module and kept ready by `window-overview.service`.
Other desktop features may still use Quickshell independently.

Captures are full resolution. Thumbnails use SIMD Lanczos downscaling, and labels
are rendered separately at the output resolution. The expanded preview copies source
pixels directly at 100%. Text necessarily becomes smaller when several complete
workspaces fit on one screen; expand a workspace or preview for original-size
text. Captures refresh once a second while visible, scaled images and glyphs are
cached, unchanged captures reuse their cache, and the daemon sleeps while closed.
Browser/editor tabs internal to an app remain part of that app's window.

Diagnostics:

```sh
window-overview --list             # Fresh Hyprland snapshot as JSON
window-overview state              # UI state, capture sizes and render time
window-overview view workspaces
window-overview scope all          # Or: scope current
window-overview back               # Leave an expanded workspace
window-overview open
window-overview inspect 1          # Expand window 1 at original resolution
window-overview dump /tmp/overview.png
window-overview hide
systemctl --user status window-overview.service
```

Rust tests cover spatial coordinates (including negative monitor origins), stable
numbering when filtering, overlapping windows, rotation/scale and pixel-exact
native cropping, set scoping, search across sets, hiding empty workspaces,
keyboard shortcut mapping, browsing filtered results, set containment in
Workspaces, and flat window results across sets.
Workspace-set tests cover activation without exposing parked workspace names.
The Nix package runs the Rust tests during its build.
