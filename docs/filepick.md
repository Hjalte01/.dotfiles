# Filepick

Rust file picker for finding files across folders, selecting a group, and attaching
them to Firefox or opening them for dragging. Installed on both hosts by
`home-manager/common.nix`; the desktop adds the launcher and Dragon drag window.

Open with **Super+Alt+F**, or run `filepick`. It opens a cached index of your
documents, downloads, desktop, pictures, videos, music, project folders, dotfiles,
and Zotero PDFs. Application state, games, caches, dependencies, generated output,
and model/data artifacts are excluded by default. Type parts of a filename or
path; matching and index updates happen in background workers. Separate search terms with spaces,
for example `thesis .pdf`; `'report` matches literal text and `!draft` excludes it.
Press **Esc** to use Vim keys.

| Key | Action |
| --- | --- |
| `j` / `k`, arrows | Move down / up |
| `gg` / `G` | First / last match |
| `Ctrl+D` / `Ctrl+U` | Half-page down / up in normal mode |
| `Space` | Toggle current file in normal mode |
| `Tab` / `Shift+Tab` | Toggle and move down / up in either mode |
| `v`, then `j` / `k` | Select a range; `v` or `Esc` finishes it |
| `a` / `Ctrl+A` | Add all current matches to the selection |
| `x` / `Ctrl+X` | Clear the selection |
| `/` / `i` | New search / edit current search |
| `Enter` | Attach selected files to the original Firefox input; otherwise copy |
| `y` | Copy selected files without attaching |
| `d` | Copy and open a drag window |
| `Y` | Copy paths as text and close |
| `Ctrl+R` | Switch between personal and system search |
| `.` | Include or exclude hidden, ignored, and generated files, in normal mode |
| `r` | Force an index rebuild, in normal mode |
| `?` | Help, in normal mode |
| `q` / `Ctrl+C` | Quit (`q` in normal mode) |

Selections persist across searches and root changes. If nothing is marked,
copy/drag uses the highlighted file. The right pane previews text and lists the
selection when the terminal is wide enough. Visual mode freezes result order
until the range is finished.

## Attach files to a Firefox input

1. Click the ChatGPT message input (or another Firefox input that accepts pasted files).
2. Press **Super+Alt+F**, search, and press `Tab` on each file you want.
3. Press **Enter**. The original Firefox window regains focus, and every selected
   file is pasted into its previously focused input automatically. No manual
   paste or drag window is needed. This attaches files without submitting the message.

Firefox on Linux currently exposes only the first file from a clipboard URI
list. Filepick works around this by publishing and pasting one selected file at
a time, waiting for Firefox to read each file URI before advancing, then restoring
the complete selection to the clipboard. The desktop launcher remembers the exact window address, class, and process ID before taking
focus. If that window closes or another window gains focus during the sequence,
attachment stops and the selection remains available for manual dragging.

Automatic attachment is limited to Firefox/LibreWolf through the desktop
launcher. The website must accept file paste; a native HTML file chooser or a
site accepting only drops still needs the drag action. File type, size, count,
and upload restrictions depend on the destination. Press `Esc`, then **y** to
copy the selection without attaching it. When opened from another application or
run directly from a terminal, Enter copies files instead of pasting automatically.

For manual dragging, press **Esc**, then **d** in the picker. Hold the left mouse
button on its file group, drag it onto the upload area, and release; every selected
file is included in that drag. The drag window closes after a completed drop.
**Super+Alt+D** also opens the last selection for dragging after the picker closes.

File copying offers `text/uri-list`, GNOME's copied-files format (copy, never cut),
KDE's copy marker, and plain-text absolute paths for the entire selection
through a Rust Wayland clipboard owner. A separate process
keeps those formats available after the picker closes, until another clipboard
owner replaces them. `Y` offers only plain file paths; useful when you explicitly
want text even in an application that also understands file references.

The saved selection contains file references, not copies of their contents. It
lives in `$XDG_STATE_HOME/filepick/selection`, normally
`~/.local/state/filepick/selection`, in a private directory with a private file.
Moving or deleting a selected file before pasting makes its reference unavailable.
Enter in the Firefox workflow starts the site's normal attachment/upload handling;
it does not press the site's send/submit button. Copying with `y` or `Y` alone
does not upload anything.

## Commands and scope

```sh
filepick ~/Documents                 # Search a particular folder
filepick --system                    # Search readable files under /
filepick --all                       # All home files, including hidden/generated files
filepick --refresh                   # Open cached results and force a rebuild
filepick --index                     # Update the index without opening the picker
filepick --query 'lecture .pdf'       # Start with a query
filepick --copy ~/Downloads/a.pdf ~/Pictures/b.png
filepick --drag-last                 # Reopen last selection for dragging
filepick --print                     # Print paths; works over SSH without Wayland
filepick --print0                    # NUL-delimited output for scripts
```

System search skips `/proc`, `/sys`, `/dev`, `/run`, and `/nix`; inaccessible
directories are counted and skipped. An explicit folder searches that folder
instead of the personal roots. Project `.gitignore`, `.ignore`, and
`.filepick-ignore` rules are respected. Hidden folders and files, caches,
dependencies, datasets, model weights, databases, logs, and build output are
excluded by default. `--all` or `.` bypasses these filters. An explicit hidden
root such as `filepick ~/.config` is searchable. Symlink directories are not
followed, avoiding cycles. The picker selects regular files.

## Cache and configuration

Indexes contain file paths and folder/ignore-file metadata; file contents are
not cached. They live in `$XDG_CACHE_HOME/filepick` (normally
`~/.cache/filepick`) in private files, separate for each root and filter mode.
Writes are atomic; a missing or damaged cache triggers a fresh scan.

On reopening, cached paths appear first. Only folder and ignore-file timestamps
are checked, rather than enumerating every file again. If they changed, the
filtered index rebuilds in the background and replaces the old results; selected
paths are preserved. Creating, deleting, or renaming files and changing ignore
rules triggers this check. Editing an existing document does not need a rebuild.
Very recent filesystem changes can share a timestamp; `r` or `--refresh` forces a
rebuild when needed. A systemd user timer runs `filepick --index` every two
minutes to keep the default index prepared. Unchanged indexes skip traversal.
The idle picker also avoids redrawing the terminal when nothing changed.

Personal roots and extra gitignore-style exclusions are managed declaratively in
`home-manager/common.nix`, installed as `~/.config/filepick/roots` and
`~/.config/filepick/ignore`. Roots are relative to home or absolute, one per line;
blank lines and comments are ignored. Change their source and run `nxb` to apply.
Changes to either configuration automatically select a new cache. Use a local
`.filepick-ignore` in a project for further exclusions. `--all` remains the escape
hatch for files hidden by the default policy. The index's own cache is always
excluded from recursive searches.

The terminal picker works on the VPS with `--print` or `--print0`. Clipboard
copying needs a Wayland compositor supporting data control (such as Hyprland),
and dragging needs the desktop's `dragon-drop` package and a graphical session.

## Development

```sh
nix shell nixpkgs#cargo nixpkgs#rustc nixpkgs#rustfmt nixpkgs#clippy
cargo test --manifest-path pkgs/filepick/Cargo.toml
cargo clippy --manifest-path pkgs/filepick/Cargo.toml --all-targets -- -D warnings
```

The Nix package builds from `Cargo.lock` with a pinned dependency hash and runs
the Rust tests during builds. Rebuild and activate dotfiles changes with `nxb`.
