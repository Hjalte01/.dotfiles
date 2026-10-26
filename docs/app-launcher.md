# App launcher priorities

Super+Space opens the app launcher. Super+Shift+Space opens it fullscreen.
Normal apps appear first, followed by lower-priority apps. Both groups retain
frequency ordering from the previous Rofi launcher, then sort alphabetically.
Search matches app names, keywords and descriptions without mixing the groups.
Typing a game's name still makes it easy to launch.

Select an app and press **Ctrl+P** to toggle between normal and lower priority.
A small grey dot beside the app name marks lower priority. Changes save
immediately; the search and selected app stay in place when the list reorders.
New applications default to normal priority.

The launcher shows a subtle **Ctrl+?** hint. Press **Ctrl+?** (or Ctrl+/) to
expand the shortcut help, and again to collapse it. Enter opens the selected
app, arrow keys change the selection, and Escape closes the launcher.

Lutris, Roblox (Sober), Roblox Studio, Steam, Prism Launcher, GeForce Now, and
the existing game shortcuts and game launchers start in the Lower group. The
inline priority toggle can override these defaults. App preferences are writable user state in
`~/.config/app-launcher/priorities.json`, keyed by desktop entry ID. Launch
counts live in `~/.local/state/app-launcher/history.json`; the initial counts
come from `~/.cache/rofi3.druncache`. Home Manager installs the launcher
declaratively in the desktop module.
