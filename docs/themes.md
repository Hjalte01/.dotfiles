# Themes and wallpapers

Open **Super+T → C** to choose Catppuccin Mocha (the default), Catppuccin
Latte (light), Tokyo Night, Nord, Gruvbox, or Rosé Pine. Choices apply at
runtime and survive rebuilds and logins. The picker and switching engine are
implemented in Rust. Hover a row, or move with arrows / J/K, to preview it across
your desktop and apps. Click or press Enter to save. Escape, Cancel, or closing
the picker restores your saved theme. Previewing never changes the saved choice.

**Super+T → W** opens the wallpaper picker with previews. Each palette includes
nine original 3840×2160 backgrounds. **Super+T → V** cycles the whole collection:

- Alpine — mountain dusk, with the app theme's colors.
- Flow — flowing color ribbons, with the app theme's colors.
- Orbit — a quiet solar system, with the app theme's colors.
- Daybreak — a warm ivory sky, peach sun, and layered terracotta dunes.
- Lagoon — a bright turquoise coast with seafoam and sandy shores.
- Bloom — sculptural pastel petals on a soft blush background.
- Bauhaus — bold navy, ochre, and rust geometry on warm cream.
- Spectrum — a saturated teal, violet, and coral wave.
- Botanical — illustrated sage foliage on pale linen green.

The six newer designs retain their own light or colorful backgrounds across
all app themes, with subtle accents drawn from the active palette. Bright
wallpapers can therefore be paired with dark apps as well as Catppuccin Latte.
The picker and cycle share the generated `wallpapers.json` catalog.
The picker also lists images under
`~/Pictures/Wallpapers`, and “Open image…” browses elsewhere.
Each theme remembers its own wallpaper. Personal images are copied into the
theme state directory, so moving the original does not break the background.

The palette covers Hyprland borders, Waybar, Rofi (including existing menus),
Ghostty's background and ANSI colors, mako, SwayOSD, GTK 3/4 and libadwaita,
Qt 5/6 via Fusion/qtct, Neovim, tmux, btop, Zathura's interface, and Obsidian
vaults registered with the desktop app. PDF pages retain their original colors.
Custom tools share the palette too: the key map, window overview, live dictation,
filepick, Hendrix, and microphone/output priority TUIs.

Ghostty, Neovim, tmux, notifications, and the custom tools reload without losing
their sessions. Existing Neovim and TUI processes must be reopened once after
first installing this integration; subsequent theme changes update them live.
Some GTK/Qt applications, btop and Zathura may need to be reopened to pick up
changed colors. Qt's platform integration takes effect for newly launched apps
after a desktop login. Firefox and other apps that follow the system appearance
receive the light/dark preference; application-specific themes and websites that
ignore it retain their own styling. Independently themed apps such as Spotify
and Blender are not recolored by this integration.

The command line supports:

```sh
system-theme menu
system-theme list
system-theme set nord
system-theme next
system-theme wallpaper
system-theme wallpaper ~/Pictures/my-background.jpg
system-theme wallpaper-next
system-theme status
system-theme apply
system-theme preview nord  # temporary, without changing saved state
system-theme cancel        # restore the saved theme
```

Palette definitions live in `themes/palettes.json`. `scripts/theme-assets.py`
builds the catalog and renders the SVG wallpaper designs with resvg in Nix.
The runtime lives in `pkgs/system-theme/`, with a native GTK layer-shell picker,
serialized/coalesced hover previews and direct Hyprland IPC. Ghostty is signalled
by its real executable path, including Nix's `.ghostty-wrapped` binary. Existing
Neovim sessions receive a direct RPC notification for immediate updates. A wallpaper
service watches the selected image instead of restarting on every hover.
`home-manager/themes.nix` is imported from the common profile; desktop adapters
are enabled only in `home-manager/home.nix`. The VPS shares Neovim, tmux, btop,
filepick, Hendrix, and the command-line selector without desktop services.

Generated assets are immutable under `~/.config/dotfiles-theme/catalog`.
The atomically updated `current` symlink selects one palette for every adapter.
Preferences and personal wallpaper copies live in
`~/.local/state/dotfiles-theme`. Existing writable app settings keep unrelated
preferences and receive a one-time `.before-system-theme` backup. Obsidian
uses an enabled `dotfiles-theme.css` snippet in each registered vault.
