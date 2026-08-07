# Coherent desktop keybindings PRD

Status: implemented and activated on 2026-08-06 after approval of the Go sequence.

## Problem

The live Hyprland configuration contains good local patterns, but no single global
grammar. In particular, the web shortcuts use `Super+Shift`, `Super+Ctrl`, and
`Super+Shift+Ctrl` interchangeably. Several special laptop keys are also rewritten
by `keyd` into ordinary `Super+letter` chords, which makes intentional shortcuts
look duplicated and consumes useful key combinations.

The redesign should make a binding predictable from its purpose, avoid chords with
three modifiers, retain strong existing muscle memory, and keep every shortcut
discoverable in the existing keybind manual.

## Evidence from the current system

The repository and the live `hyprctl binds` table agree on the active bindings.
Notable problems are:

- Web destinations span 2, 3, and 4 simultaneous keys.
- `Super+P` and synthetic `Super+t` both open the display menu.
- `Super+m` and `Super+i` both open the keybind manual.
- `Super+Ctrl+o` and `Super+Ctrl+s` both toggle autoscroll.
- Area and monitor screenshots each have both a Print-key binding and a longer
  `Super` chord.
- The display menu's fullscreen variant, Docker, and three web destinations use
  four simultaneous keys.
- Notification history and split rotation have logically related variants, but
  require a third modifier for those variants.
- `keyd` currently maps `switchvideomode` to `Super+t`, and maps both `nextsong`
  and `F9` to `Super+m`. These hardware translations are the source of some
  apparent aliases and should not define the desktop shortcut namespace.

The usage cache contains only three manually viewed entries, so it is not strong
enough evidence for frequency-based remapping. The proposal therefore preserves
the established window, workspace, launcher, and clipboard groups.

## Design rules

1. `Super` is the desktop leader.
2. Direct `Super+key` bindings are frequent primary actions.
3. `Shift` means the paired alternate action, such as move, swap, all, fullscreen,
   or rotate.
4. `Ctrl` means toggle, capture, or maintenance.
5. `Alt` means adjust, resize, settings, or history.
6. Website destinations live behind one memorable sequence prefix: `Super+G`
   means **Go**. After releasing it, one mnemonic key chooses the destination.
7. No intentional shortcut may require more than two simultaneous modifiers.
8. Hardware/Fn keys emit their proper key events and are bound by key name; they
   must not masquerade as ordinary `Super+letter` shortcuts.
9. Every active binding and sequence appears correctly in the keybind manual.

These rules describe intent rather than forcing every old shortcut into a modifier
layer. A familiar, self-explanatory binding such as `Super+Enter` is better than a
technically uniform but harder-to-remember replacement.

## Options and scores

Scores are weighted as follows: learnability/mnemonics 35%, consistency 25%,
ergonomics 15%, speed 15%, and collision-free growth 10%.

| Scheme | Learnability | Consistency | Ergonomics | Speed | Growth | Total |
|---|---:|---:|---:|---:|---:|---:|
| Current configuration | 17/35 | 10/25 | 7/15 | 15/15 | 4/10 | **53/100** |
| Normalize all launches to `Super+Shift+letter` | 26/35 | 21/25 | 11/15 | 15/15 | 5/10 | **78/100** |
| One `Super+G` Rofi web menu | 34/35 | 25/25 | 14/15 | 9/15 | 10/10 | **92/100** |
| `Super+G` mnemonic web sequence + modifier grammar | 34/35 | 25/25 | 14/15 | 14/15 | 10/10 | **97/100** |

The direct-launch scheme improves chord consistency but cannot give every service
its natural letter: ChatGPT conflicts with Codeforces, and two email and two KU
destinations collide. A Rofi menu is extremely discoverable but makes frequent
destinations slower. The recommended sequence scheme resolves both issues: only
`Super+G` is held, the second key is mnemonic, and the sequence can show a brief
on-screen cheat sheet while it is active.

## Proposed bindings

### Web and online destinations

Press and release `Super+G`, then press one key. The sequence exits immediately
after a destination launches; `Escape` cancels it.

| Sequence | Action | Mnemonic | Current binding |
|---|---|---|---|
| `Super+G`, `f` | Firefox with Google in a new window | Firefox | `Super+Ctrl+B` |
| `Super+G`, `g` | Gemini | Gemini | `Super+Shift+A` |
| `Super+G`, `p` | ChatGPT | Prompt / GPT | `Super+Shift+Ctrl+A` |
| `Super+G`, `a` | Absalon | Absalon | `Super+Ctrl+K` |
| `Super+G`, `k` | KUnet | KU | `Super+Shift+Ctrl+K` |
| `Super+G`, `e` | Personal email | Email | `Super+Shift+E` |
| `Super+G`, `u` | KU email | University | `Super+Shift+Ctrl+E` |
| `Super+G`, `y` | YouTube | YouTube | `Super+Shift+Y` |
| `Super+G`, `d` | Discord | Discord | `Super+Shift+D` |
| `Super+G`, `c` | Codeforces session | Codeforces | `Super+Shift+C` |

The Calculator hardware key remains the direct WolframAlpha shortcut. The commented
private-browser and Tor shortcuts are not activated; if enabled later, use `i` for
incognito/private and `t` for Tor within the same sequence.

### Direct application launches

All dedicated application launches use `Super+Shift+mnemonic`; the especially
frequent terminal keeps the standard `Super+Enter` binding.

| Proposed | Action | Current |
|---|---|---|
| `Super+Enter` | Terminal | unchanged |
| `Super+Shift+F` | Downloads/files | unchanged |
| `Super+Shift+N` | Neovim | unchanged |
| `Super+Shift+B` | btop | `Super+Shift+T` |
| `Super+Shift+D` | lazydocker | `Super+Shift+Ctrl+D` |
| `Super+Shift+Z` | Zathura | unchanged |

### Clean up paired actions and aliases

| Proposed | Action | Current / disposition |
|---|---|---|
| `Print` | Area screenshot | keep; remove `Super+Shift+S` alias |
| `Alt+Print` | Active-monitor screenshot | keep; remove `Super+Shift+Alt+S` alias |
| `Super+P` | Display menu | keep |
| `Super+Shift+P` | Display menu fullscreen | replace `Super+Ctrl+Shift+T` |
| `Super+m` | Keybind manual | keep; remove `Super+i` alias |
| `Super+Shift+m` | Keybind manual fullscreen | keep |
| `Super+Ctrl+s` | Toggle autoscroll | keep; remove `Super+Ctrl+o` alias |
| `Super+R` | Swap active split | replace `Super+Alt+R` |
| `Super+Shift+R` | Rotate active split | replace `Super+Alt+Shift+R` |
| `Super+Ctrl+R` | Reload desktop configuration | replace `Super+Shift+R` |
| none | Restart Waybar only | remove `Super+Shift+W`; desktop reload already restarts Waybar |
| `Super+,` | Dismiss one notification | unchanged |
| `Super+Shift+,` | Dismiss all notifications | unchanged |
| `Super+Ctrl+,` | Toggle notification popups | unchanged |
| `Super+.` | Notification history | replace `Super+Alt+,` |
| `Super+Shift+.` | Notification history fullscreen | replace `Super+Alt+Shift+,` |

The adjacent comma/period pair reads as **dismiss/history**, while Shift consistently
means the larger-scope variant.

### Groups intentionally preserved

- `Super+H/J/K/L` focuses; adding Shift swaps; adding Alt resizes.
- `Super+1..0` changes workspace; adding Shift moves the window.
- `Super+Space` opens the launcher; Shift opens its fullscreen variant; Ctrl toggles
  Waybar.
- `Super+V` opens clipboard history; Shift makes it fullscreen; Ctrl captures the
  current clipboard for Codex; Alt captures clipboard history.
- `Super+Ctrl+N` toggles night light and `Super+Alt+N` opens its menu.
- Media, volume, brightness, microphone, and Calculator keys keep direct hardware
  behavior.
- `Super+W`, `Super+F`, mouse window movement, system power, Bluetooth, pavucontrol,
  active-app mute, accessibility toggles, Talon microphone selection, Math OCR, and
  Codex launch remain unchanged unless runtime collision testing finds a problem.

## Hardware-key normalization

The implementation should change the main-PC `keyd` mappings so special keys emit
named events instead of `Super+letter` chords:

- `switchvideomode` should emit `display`, handled in Hyprland as `XF86Display` and
  opening the same display menu as `Super+P`.
- `nextsong` should emit `nextsong`, already handled as `XF86AudioNext`.
- The physical key currently reported as `F9` should emit `F9`. If that physical
  key is intended to open the manual, bind `F9` explicitly instead of translating
  it to `Super+m`.
- The physical dictation key currently reaches the `Super+D` binding while the
  script describes it as F11. Record its raw event with `keyd monitor` before
  changing it; then bind the actual named key directly and free `Super+D` if the
  device permits it.

This portion is deliberately conditional on event capture because the two input
devices may report the same physical laptop key differently. No guessed remap
should disable a hardware button.

## Implementation plan

1. Capture each affected laptop key with `keyd monitor` (display, next, F9/manual,
   and F11/dictation) and record the input device and raw event.
2. Update the desktop-only `services.keyd.keyboards` mappings in
   `nixos/configuration.nix` to emit named events.
3. Add the `Super+G` Hyprland submap, its ten destination bindings, automatic reset,
   `Escape` cancellation, and a visible short cheat sheet/submap indicator.
4. Apply the direct application and paired-action mapping tables above; delete the
   superseded aliases rather than retaining a second hidden grammar.
5. Extend `scripts/custom-keybinds` so sequences render as, for example,
   `Super+G → G`, rather than incorrectly displaying their second-stage keys as
   global bindings.
6. Add a lightweight validation script or check that rejects duplicate active
   chords, unintended three-modifier chords, and undocumented submap bindings.
7. Run syntax/static checks, then run `nxb` as required for flake-managed dotfile
   changes.
8. Verify the live state with `hyprctl -j binds`, exercise every changed shortcut,
   confirm submap cancellation/reset, and test the affected hardware keys on the
   laptop keyboard.
9. Refresh/open the keybind manual and verify every displayed sequence and command.

## Acceptance criteria

- All ten current online destinations work through `Super+G` plus one mnemonic key.
- No online destination needs Ctrl, Alt, or three simultaneous modifiers.
- No intentional active shortcut contains three modifiers.
- There are no duplicate action aliases except an explicitly documented hardware
  key paired with one keyboard shortcut.
- Hardware display, media-next, manual/F9, and dictation/F11 behavior still works.
- The keybind manual shows global bindings and sequences accurately.
- `hyprctl -j binds` matches the approved mapping, the Hyprland config reloads
  without errors, and `nxb` succeeds.

## Implemented decisions

1. The approved `Super+G`, then mnemonic-key web sequence is active.
2. `p` selects ChatGPT (**p**rompt/GPT), leaving `c` for Codeforces.
3. `u` selects KU email (**u**niversity), leaving `e` for personal email.
4. Superseded aliases were removed immediately.
5. `F9` is bound directly to the keybind manual; its `keyd` translation now emits
   `F9` instead of synthetic `Super+m`.
