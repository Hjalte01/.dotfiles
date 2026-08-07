# Desktop Which-Key Overlay PRD

Status: proposed for review; no overlay or bindings have been changed.

## Summary

Build a LazyVim/which-key-inspired desktop overlay for Hyprland. It should expose
the complete custom key map with concise descriptions, show only relevant
continuations while a sequence such as `Super+G` is active, and optionally appear
after holding Super without intercepting the shortcut that follows.

The recommended design is a small, persistent Quickshell service with three views:

1. **Peek:** hold Super for 450 ms to see the Super key map; release Super to hide.
2. **Pinned:** press `Super+M` to toggle the complete key map.
3. **Context:** press `Super+G` to show only the web destination keys until a choice
   or Escape resets the submap.

`Super+Shift+M` retains the current searchable Rofi manual as a fallback for fuzzy
search and accessibility.

## Why it is called which-key

LazyVim uses the `which-key.nvim` plugin. It shows valid continuations after a
prefix and gives each key a short description. The desktop version should copy the
interaction model and visual hierarchy, not the exact Neovim implementation.

## Current-state evidence

- The current parser exposes 101 documented actions, including 11 entries in the
  web submap.
- There are 76 global Super-family chords but only 36 distinct terminal keys.
- The busiest keys are `L`, `M`, and `V`, each with four modifier variants.
- Repeated patterns can be represented compactly without hiding information:
  `H/J/K/L` for directions and `1–0` for workspaces.
- Every parsed binding already has a description; no `Unnamed` rows need manual
  repair.
- Rofi is installed and useful for fuzzy search, but it takes keyboard focus. It
  therefore cannot remain open while Hyprland receives the next key in a submap.
- Quickshell 0.3.0 is available in the current flake's Nixpkgs.

Hyprland officially supports described bindings, release bindings, modifier-only
bindings, and non-consuming bindings. Quickshell's `PanelWindow` defaults to not
accepting keyboard focus, and its IPC handler can change an existing shell's state
without starting a new UI process. These APIs make a non-interfering contextual
overlay feasible:

- [Hyprland binding documentation](https://wiki.hypr.land/Configuring/Basics/Binds/)
- [Quickshell PanelWindow](https://quickshell.org/docs/v0.3.0/types/Quickshell/PanelWindow/)
- [Quickshell IPC handler](https://quickshell.org/docs/v0.3.0/types/Quickshell.Io/IpcHandler/)
- [Quickshell process/data loading](https://quickshell.org/docs/v0.3.0/types/Quickshell.Io/Process/)

Existing Hyprland shells also use Quickshell for generated keybind cheat sheets,
which is useful prior art, although this implementation should stay small and
native to these dotfiles rather than importing an entire shell:

- [end-4 dotfiles](https://github.com/end-4/dots-hyprland)
- [Noctalia keybind cheat-sheet plugin](https://noctalia.dev/plugins/keybind-cheatsheet)

## Requirements

### Functional

- Show every active custom binding and a short description in the pinned view.
- Show all Super-family bindings when peeking with Super held.
- Show only valid second-stage keys when a Hyprland submap is active.
- Never take keyboard focus in peek or contextual mode.
- Keep the underlying Hyprland bindings operational while the overlay is visible.
- Automatically reflect additions, removals, descriptions, and submap changes from
  `hypr/hyprland.conf`; there must not be a second hand-maintained key list.
- Display on the focused monitor and respond correctly to its scale.
- Provide an explicit toggle that works even if hold-to-peek is disabled.
- Preserve the searchable Rofi manual.
- Fail open: if the overlay process is unavailable, all actual shortcuts and
  submap cancellation must continue to work.

### Visual

- Use the existing Catppuccin Mocha palette: base `#1e1e2e`, surface `#313244`,
  text `#cdd6f4`, muted text `#a6adc8`, and mauve accent `#cba6f7`.
- Use JetBrainsMono Nerd Font and rounded keycaps.
- Put the key before the description so the eye can scan vertically.
- Group actions by purpose rather than presenting one long alphabetical list.
- Render modifier variants beneath their base key with compact colored badges:
  `⇧` for Shift, `Ctrl`, and `Alt`.
- Use a short 120–160 ms fade/slide animation; no bouncing or long transitions.
- Remain readable at both laptop and external-monitor scales.

## Interaction model

### 1. Hold-to-peek

- Press and hold either Super key.
- A non-consuming controller waits 450 ms. If Super is still held, it requests the
  `super` view over Quickshell IPC.
- Releasing Super immediately hides a peek view.
- Normal fast shortcuts should finish before the delay and never flash the overlay.
- If reliable press/release detection cannot be achieved without consuming or
  delaying Super, this feature fails its implementation gate and is disabled. The
  explicit toggle remains the reliable primary path.

Delay comparison:

| Delay | Benefit | Cost | Score |
|---|---|---|---:|
| 250 ms | Very responsive | Likely to flash during deliberate shortcuts | 72/100 |
| **450 ms** | Fast enough to discover, slow enough to avoid normal chords | Slight pause before help | **94/100** |
| 700 ms | Few accidental appearances | Feels sluggish | 81/100 |

### 2. Explicit toggle

- `Super+M` toggles a pinned **All bindings** view. `M` means map/manual and is
  already the established manual key, so this does not consume a new mnemonic.
- `F9` performs the same toggle for the laptop's dedicated manual key.
- A pinned view is not dismissed by releasing Super.
- Pressing `Super+M` again closes it.
- `Super+Shift+M` continues to open the current searchable/fullscreen Rofi manual.

Toggle-key comparison:

| Key | Reason | Layout/conflict cost | Score |
|---|---|---|---:|
| **`Super+M`** | Map/manual; already learned | None | **99/100** |
| `Super+/` | Common cheatsheet convention | Awkward on Danish layout and implies Shift | 79/100 |
| `Super+I` | Information | Weaker mnemonic and a newly consumed key | 74/100 |

### 3. Contextual sequence view

- `Super+G` switches the same overlay to a `Web` context.
- The window remains non-focusable, so `F/G/P/A/K/E/U/Y/D/C` continue to reach
  Hyprland's `web` submap.
- Choosing a destination or pressing Escape hides the overlay and resets the
  submap.
- This replaces the current Mako cheat-sheet notification, avoiding two visual
  systems for the same concept.

## Information architecture

The parser groups source bindings into these sections:

- Launch & open
- Windows & layout
- Workspaces
- Clipboard & Codex
- Display & desktop
- Accessibility & automation
- Notifications & screenshots
- Hardware & media
- Sequences

Bindings that share their final key become one visual family. For example:

```text
┌──────────────────── Desktop Which-Key ────────────────────┐
│  SUPER · ALL BINDINGS                  M: unpin · ⇧M: search│
│                                                            │
│  LAUNCH & OPEN       WINDOWS             CLIPBOARD & TOOLS │
│  [Enter] Terminal    [H J K L] Focus     [V] Clipboard     │
│  [Space] Apps        [⇧ H J K L] Swap        ⇧ Fullscreen  │
│      ⇧ Fullscreen    [Alt H J K L] Resize    Ctrl Capture  │
│  [G] Websites  ›     [F] Fullscreen          Alt History   │
│  [N] Neovim          [W] Close           [C] Codex         │
│      ⇧ launch                             [L] Math OCR      │
│                                                            │
│  WORKSPACES          DISPLAY & SYSTEM     HARDWARE         │
│  [1–0] Switch        [P] Display          [Vol±] Volume    │
│      ⇧ Move              ⇧ Fullscreen     [Print] Area     │
│  [Mouse1] Move           Ctrl Audio       [F9] This map     │
└────────────────────────────────────────────────────────────┘
```

The wireframe illustrates hierarchy, not the final row allocation. No binding is
discarded when a family is collapsed: each modifier variant remains visible under
the key family, and hovering/clicking is not required to reveal it.

## Candidate implementations and scores

Weights: visual scanability 25%, contextual accuracy 20%, non-interference and
reliability 20%, learnability 15%, speed 10%, maintainability 10%.

| Candidate | Visual | Context | Reliability | Learnability | Speed | Maintenance | Total |
|---|---:|---:|---:|---:|---:|---:|---:|
| Current Rofi manual + Mako web hint | 10/25 | 6/20 | 16/20 | 9/15 | 5/10 | 8/10 | **54/100** |
| Restyled Rofi-only manual | 19/25 | 7/20 | 11/20 | 13/15 | 7/10 | 9/10 | **66/100** |
| Import a full third-party Quickshell shell/plugin | 22/25 | 15/20 | 16/20 | 13/15 | 8/10 | 5/10 | **79/100** |
| Small custom Quickshell, explicit toggle only | 24/25 | 17/20 | 19/20 | 14/15 | 8/10 | 9/10 | **91/100** |
| **Custom Quickshell: toggle + contextual + gated Super peek** | 24/25 | 20/20 | 17/20 | 15/15 | 10/10 | 9/10 | **95/100** |

The hybrid is recommended. It provides the direct LazyVim-like experience while
retaining a reliable explicit toggle and a searchable fallback. Its only material
risk is modifier-only press/release behavior; the implementation gate prevents
that optional feature from compromising ordinary shortcuts.

## Architecture

### Source of truth

- Extend the existing keybind parser with a machine-readable JSON mode.
- Preserve `bindd` descriptions and `# keybind:` descriptions.
- Add lightweight `# keybind-group:` metadata to semantic blocks where necessary.
- Include fields for scope/submap, modifiers, final key, description, command,
  group, and compact-family identity.
- Continue excluding hardware switch events and deliberate `exec, true` swallow
  bindings.
- Make the collision validator consume the same parsed representation.

### Overlay service

- Add Quickshell only to the desktop Home Manager configuration.
- Store the small dedicated configuration under
  `.config/quickshell/keybind-hints/`.
- Run it as a restartable user service rather than launching a full process for
  every reveal.
- Use a non-focusable layer-shell `PanelWindow` above normal windows with no
  exclusive zone.
- Use Quickshell IPC calls: `show super`, `show all`, `show web`, `hide`, and
  `toggle all`.
- Select the focused Hyprland monitor and adapt columns to available width.
- Reload keybind JSON when the Hyprland config changes or immediately before show.

### Controller

- Provide one `desktop-which-key` helper that wraps IPC and safely no-ops if the
  overlay is unavailable.
- Track peek and pinned states separately so releasing Super cannot close a pinned
  manual.
- Update `web-shortcuts` to call contextual show/hide while keeping its own submap
  reset logic independent.
- Keep Rofi parsing/searching in `custom-keybinds`; it remains the fallback rather
  than being deleted.

## Implementation plan

1. Add JSON/group output and fixtures/tests to the existing keybind parser.
2. Add semantic group annotations to the Hyprland config and verify that all 101
   current displayed actions remain represented.
3. Build the Quickshell overlay with static fixture data first and check laptop and
   external-monitor layouts.
4. Connect live parser data and Quickshell IPC; test `show`, `hide`, context changes,
   service restarts, and config reloads.
5. Replace the Mako web hint with the `web` contextual view while preserving web
   launch/reset behavior.
6. Change `Super+M` and F9 to toggle the pinned overlay; retain
   `Super+Shift+M` for the searchable Rofi manual.
7. Prototype non-consuming Super press/release binds behind a feature flag. Run at
   least 50 ordinary Super shortcuts and verify zero accidental overlays, lost
   keystrokes, or delayed actions before enabling hold-to-peek by default.
8. Add failure-path tests proving shortcuts and Escape cancellation work with the
   Quickshell service stopped.
9. Run ShellCheck, parser/fixture tests, duplicate/modifier validation, QML checks,
   Hyprland reload checks, and `nxb`.
10. Verify the deployed UI and capture screenshots on both monitor sizes for final
    visual review.

## Acceptance criteria

- `Super+M` and F9 toggle a polished complete key map on the focused monitor.
- Every active custom action currently exposed by the parser appears with a useful
  description, either directly or as an explicitly visible family variant.
- `Super+Shift+M` still opens a searchable keybind manual.
- `Super+G` shows the ten web continuations in the new overlay, and every
  continuation plus Escape still works.
- Peek/context views never take keyboard focus.
- If enabled, holding Super for about 450 ms reveals the Super-family map and
  releasing it hides the map.
- Fifty representative quick Super shortcuts produce zero help-overlay flashes,
  lost keys, or action delays.
- Stopping Quickshell does not break any real shortcut or leave Hyprland trapped in
  a submap.
- The overlay is readable and correctly scaled on the laptop and external monitor.
- Parser output, overlay entries, and `hyprctl -j binds` agree on scope, key, and
  description.
- `nxb` succeeds and the live system matches the repository.

## Review decisions

Please approve or change these before implementation:

1. Use `Super+M` for the pinned all-bindings overlay and retain
   `Super+Shift+M` for searchable Rofi.
2. Enable hold-Super peek only if the 50-shortcut non-interference gate passes.
3. Use a 450 ms hold delay.
4. Replace the current Mako `Super+G` hint with the same Quickshell visual system.
5. Use the Catppuccin/JetBrainsMono grouped-column design in the wireframe.

