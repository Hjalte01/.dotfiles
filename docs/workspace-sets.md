# Workspace sets

**Super+E** opens the same menu to choose an existing set or create a new one.
**Super+Shift+E** goes back to the previous set; repeat it to toggle between two.
The starter sets are **Current**, **School**, **Hobbies**, and **Fun**. Existing
windows belong to Current. The menu can rename the current set.

Each set has its own workspaces **1–9**. Super+number switches within the current
set; adding Shift moves the active window. Switching sets keeps whole workspaces,
including tiled layouts, fullscreen state and application contents. It restores
the workspaces visible on connected monitors and the last focused window when
available. New sets start empty. Waybar shows the current set; click its name to
open the menu or right-click to go back. Super+Tab only shows the current set.

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
```

Metadata lives in `$XDG_STATE_HOME/workspace-sets/state.json` (normally
`~/.local/state/workspace-sets/state.json`). Inactive workspaces are renamed
`set:<internal-set-id>:<slot>`; active workspaces are named `1` through `9`.
Workspace IDs and their window trees remain intact. Navigation uses workspace
names so a parked workspace's old numeric ID cannot expose it accidentally.
Set switches and keyboard workspace navigation share a lock. A journal restores
the previous names and visible workspaces if a switch fails or is interrupted.
