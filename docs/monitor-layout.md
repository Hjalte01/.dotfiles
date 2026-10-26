# Monitor layout

Open **Super+T, then P** (Desktop controls → Arrange monitor layout), or choose
**Arrange monitor layout** in the **Super+P** display menu. It also appears in
the searchable key map.

The terminal shows your active screens as boxes, with the external screen
selected initially. Match their arrangement to your desk:

- **1–9** selects the matching numbered screen box, regardless of Hyprland's
  internal monitor IDs. Numbers without a matching screen are ignored.
- **Tab / Shift+Tab** selects the next / previous screen, wrapping around;
  **A** cycles the reference screen.
- **Arrow keys** place the selected screen left, right, above or below the reference.
- **Drag a box** to position it; releasing snaps it to the nearest free edge.
- **H/J/K/L** moves by 20 logical pixels for vertical or horizontal alignment.
- **S** snaps to a shared edge; **R** reloads the current screens.
- **Enter** previews the layout. **Enter/Y** keeps it; **Esc** or waiting
  15 seconds restores the previous layout. **Q/Esc** quits outside the preview.

For today's external screen on the right: open the editor, press **Right**, then
**Enter** to preview and **Enter** again to save. Shift it up/down with **K/J**
before previewing if the screen tops are at different heights.

Screens must touch along an edge without overlapping. The shared part of that
edge determines where the mouse crosses. Sizes account for scale and rotation,
as described in the [Hyprland monitor documentation](https://wiki.hypr.land/0.52.0/Configuring/Monitors/).
Only active, independent physical screens appear; use the display menu's
**Normal extended layout** first if a display is disabled or mirrored.

Confirmed settings live in `~/.config/hypr/monitor-layout.conf`, sourced after
the desktop's default monitor rules. Home Manager creates the file if missing
and leaves saved layouts writable. Login, config reload, and reconnecting reuse
the saved position, scale, and rotation for each output. Resolution and refresh
rate use `preferred`, so each connected monitor supplies its supported native
mode instead of inheriting the previous monitor's resolution. The display menu
also restores these settings when returning to normal extended mode.

Home Manager activation converts older generated layouts to `preferred` while
preserving their positions, scales, and rotations. Files without the editor's
generated header are left alone. The same migration can be run with
`monitor-layout --migrate-saved-layout`.
Different screen sizes may still need rearranging to keep screen edges touching.
Delete the file's contents to restore defaults.

The editor and its Hyprland/Python runtime are packaged in `pkgs/monitor-layout.nix`
and installed by the desktop Home Manager module. No Python packages are downloaded
at runtime. The virtual `idle` output is excluded.
