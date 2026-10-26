# Workspace sets

**Super+E** opens the same menu to choose an existing set or create a new one.
**Super+Shift+E** goes back to the previous set; repeat it to toggle between two.
The starter sets are **Current**, **School**, **Hobbies**, and **Fun**. Existing
windows belong to Current. The menu can rename the current set.

**Super+Ctrl+Shift+E** sends the focused window to the last focused workspace in
the previous set. You stay in the current set and can repeat the shortcut to sort
more windows into that same destination. For example, visit School and then
Current; focus a misplaced window and press Super+Ctrl+Shift+E to send it to
School. Super+Shift+E takes you there to check it. If the previous set has no
saved focused workspace, the move uses the current window's workspace number.

**Super+Alt+Shift+E** sends all windows on the current workspace to the last
focused workspace in the previous set, using the same destination as the
single-window shortcut. There is no picker. Existing windows at the destination
stay and the incoming windows join their layout. You stay in the current set;
pinned windows remain shared. If no focused workspace was saved for the previous
set, the move uses the source workspace number.

For an explicit destination, run `workspace-set move-workspace-menu` to choose a
set and workspace, or `workspace-set move-workspace School 5` to move directly.

Each set has its own workspaces **1–9**. Super+number switches within the current
set; adding Shift moves the active window. Switching sets keeps whole workspaces,
including tiled layouts, fullscreen state and application contents. It restores
the workspaces visible on connected monitors and the last focused window when
available. New sets start empty. Waybar shows the current set; click its name to
open the menu or right-click to go back. **Super+Tab** offers Workspaces
and Windows views, sharing a **Current set / All sets** toggle (**Ctrl+A**).
Empty workspaces are hidden. In All sets, Workspaces groups matching workspaces
inside a named box for their set; Windows uses a flat, searchable grid.
Click a workspace heading to expand it. Selecting a window in another set
switches there first and focuses the window on the overview’s monitor,
preserving the previous-set shortcut.

The existing idle workspace **Super+0**, pinned windows, and special scratchpads
remain shared. Browser tabs stay inside their windows: use separate browser
windows for different sets. Opening a single-instance app may reuse its existing
window in another set; use the app's new-window command when needed.

Inactive sets are ordinary hidden Hyprland workspaces. They need no separate
desktop session or background manager. Apps still use RAM and can continue audio,
downloads, builds, and other background work, just as on an inactive workspace.
Set names survive logout/reboot; open applications and layouts are kept only
within the running desktop session.

```sh
workspace-set menu
workspace-set list
workspace-set switch School
workspace-set create "Exam project"
workspace-set rename "School work"
workspace-set back
workspace-set move-back
workspace-set move-workspace-back
workspace-set move-workspace-menu
workspace-set move-workspace School 5
```

Metadata lives in `$XDG_STATE_HOME/workspace-sets/state.json` (normally
`~/.local/state/workspace-sets/state.json`). Inactive workspaces are renamed
`set:<internal-set-id>:<slot>`; active workspaces are named `1` through `9`.
Workspace IDs and their window trees remain intact. Navigation uses workspace
names so a parked workspace's old numeric ID cannot expose it accidentally.
Set switches and keyboard workspace navigation share a lock. A journal restores
the previous names and visible workspaces if a switch fails or is interrupted.
Whole-workspace moves also keep a journal, returning moved windows to the source
if a move fails or is interrupted. An interrupted move is recovered by the next
workspace-set command that changes the desktop.
