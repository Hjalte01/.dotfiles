# Desktop which-key

The desktop uses a native Rust Wayland overlay, packaged declaratively in
`pkgs/desktop-which-key.nix` and run by `keybind-hints.service`. It replaces the
previous Quickshell UI and shell/systemd timer controller.

## Everyday use

| Key | Action |
| --- | --- |
| Hold either Super for 250 ms | Peek at plain Super shortcuts; release to hide |
| Super+Esc, Super+M, or F9 | Pin / close the searchable key map |
| / or Ctrl+F | Search keys and descriptions across **all** groups |
| ? while browsing, or F1 anytime | Show built-in help |
| Tab | Switch between search typing and browsing |
| Up / Down | Select a result |
| Page Up / Page Down | Browse pages |
| Home / End while browsing | First / last result |
| Enter | Run the selected action |
| Ctrl+U | Clear the query |
| Escape | Leave help, clear search, then close |
| Super+Shift+M | Fullscreen searchable Rofi fallback |

Search ignores case and matches every space-separated word against the key,
description, category, and command. Examples: `circle`, `super+ctrl+z`, `pdf`, `super+g email`.
Mouse and release gestures are reference entries; Enter does not simulate them.
Pinned mode takes keyboard focus for typing. Peek and sequence hints never do.

## Groups

Press the prefix, then its mnemonic key. Super may remain held or be released.
Escape cancels; an unknown key cancels instead of leaving the keyboard trapped.

| Prefix | Group | Continuations |
| --- | --- | --- |
| Super+G | Websites | F Firefox, G Gemini, P ChatGPT, A Absalon, K KUnet, E personal email, U KU email, Y YouTube, D Discord, C Codeforces |
| Super+A | Audio | O output hierarchy, M microphone hierarchy, P audio control panel, A mute active app |
| Super+S | System power | H hibernate, S sleep, R restart, L logout, P power off |
| Super+X | Pointer automation | A autoclicker, S autoscroll, C cursor circle |
| Super+T | Desktop controls | B Waybar, N night light toggle, L night light settings, T touchscreen, I idle monitor, R reload desktop |
| Super+C | Codex | C terminal in dotfiles, V capture clipboard, H capture clipboard history |

The pointer tools retain their existing Z-key arming behavior. They no longer
share Super+Ctrl+Z with the PDF picker.

Familiar daily actions stay direct: Super+F fullscreen, Super+Return terminal,
Super+Space launcher, Super+Tab window overview, Super+H/J/K/L focus, Shift to
swap, Alt to resize, workspace digits (Shift to move), Super+D dictation,
Super+V clipboard, Super+P display, and the existing file/PDF keys.

## Moved shortcuts

| Previous | New |
| --- | --- |
| Super+Ctrl+A / S / Z pointer tools | Super+X, then A / S / C |
| Super+Ctrl+P audio control | Super+A, then P |
| Super+Alt+M mute current app | Super+A, then A |
| Super+Ctrl+M microphone hierarchy | Super+A, then M |
| Super+Ctrl+Space Waybar | Super+T, then B |
| Super+Ctrl+N / Super+Alt+N night light | Super+T, then N / L |
| Super+Ctrl+T touchscreen | Super+T, then T |
| Super+Alt+0 idle monitor | Super+T, then I |
| Super+Ctrl+R reload | Super+T, then R |
| Super+Ctrl+C Codex terminal | Super+C, then C |
| Super+Ctrl+V / Super+Alt+V Codex capture | Super+C, then V / H |

Super+Ctrl+Z still opens the Zathura PDF picker.

## Implementation and maintenance

The Rust parser reads the **activated** `~/.config/hypr/hyprland.conf` whenever the
overlay opens. `bindd` descriptions and `# keybind:` annotations are the source of
truth. `# keybind-prefix:` associates a submap with its displayed sequence.
Descriptions are never duplicated in a separate menu definition. Hyprland config
variables are expanded for Enter-to-run; commands retain their original commas.

The daemon owns the hold timer and overlay state. Lightweight invocations send
commands over a user-private Unix socket. Super release/chord completion cancels
only peek, preserving pinned and context views. The panel follows the focused
monitor, rasterizes at its scale, and paginates rather than clipping bindings.

Super-release handlers use Hyprland's transparent (`t`) flag so a screenshot
cannot shadow them. The Yoga PrtSc firmware emits Super+Shift+S, which keyd
normalizes to Print (or Alt+Print); its synthetic Super transitions must still
cancel the peek timer after the screenshot.

Actual shortcuts and sequence cancellation remain Hyprland/script actions, so
stopping the UI does not disable them. The controller starts the service again
when needed. Desktop reload also restarts it to recover after environment changes.

Useful checks:

```sh
scripts/check-keybinds
HYPRLAND_CONFIG="$PWD/hypr/hyprland.conf" desktop-which-key --check
desktop-which-key --list
desktop-which-key state
systemctl --user status keybind-hints
journalctl --user -u keybind-hints
```

`--check` normalizes letter case and modifier order; the former validator missed
the simultaneous `Super+Ctrl+Z` PDF and cursor-circle bindings. Rust tests cover
that regression, command parsing, search, and pin/peek/context state transitions.
Run `nxb` after changing the config or implementation.

The UI uses [Wayland layer-shell keyboard interactivity](https://wayland.app/protocols/wlr-layer-shell-unstable-v1)
and [Hyprland binding flags and submaps](https://wiki.hypr.land/Configuring/Binds/).
