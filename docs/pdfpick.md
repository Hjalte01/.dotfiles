# PDF picker

Press **Super+Ctrl+Z**, or run `pdfpick`, to find a PDF and open it in Zathura.
Type parts of the filename or folder name; separate search terms with spaces.
For example, `machine learning !slides` matches both file and folder names and
excludes slides. Results keep their recent-first order while fuzzy filtering.

| Key | Action |
| --- | --- |
| `Ctrl+A` | All PDFs, newest added/changed first (default) |
| `Ctrl+D` | PDFs in Downloads and its subfolders, newest first |
| `Ctrl+O` | Previously opened PDFs, most recent first |
| `Alt+F` | Fuzzy-find a folder to restrict to it and its subfolders |
| `Alt+H` | Clear the folder restriction |
| Arrows / `Ctrl+J` / `Ctrl+K` | Move through results |
| `Tab` / `Shift+Tab` | Mark several PDFs to open together |
| `Enter` | Open the highlighted/marked PDFs in Zathura |
| `Ctrl+P` | Toggle the first-two-pages text preview |
| `Ctrl+R` | Rescan files and reread opening history |
| `Esc` / `Ctrl+C` | Close (or return from the folder selector) |

Search text and the folder restriction survive view switches. For a subject,
either type its folder name directly or use `Alt+F` to choose a course/research
folder, then search within it. A scanned or encrypted PDF may have no text preview.

The default search covers nonhidden PDFs throughout your home directory, plus
your XDG Downloads directory and existing PDFs in Zathura's history. Dependencies,
caches, and build output are skipped. Zotero's PDFs are included. File contents
are read only for the highlighted preview; search matches filenames and paths.
Empty files and PDFs with companion partial-download files are skipped. Directory
symlinks are not followed. Use an explicit root for an external drive or a hidden
folder, or `--all` to include hidden/generated files.

“Newest added” uses the later of file change time and modification time. This
finds fresh downloads even when the server supplied an old modification date;
renaming, moving, or changing permissions can also move a file up the list.
Opened history combines Zathura's existing SQLite history with immediate records
of picker launches. Zathura updates its own history when it saves document state;
an externally opened document may appear there after it closes. Missing/deleted
PDFs are omitted. The picker reads Zathura's database without modifying it.

```sh
pdfpick --view downloads
pdfpick --view opened --query 'optimization'
pdfpick ~/Documents/course ~/Zotero/storage  # Only these folders
pdfpick --all                              # Include hidden/generated folders
pdfpick --print                            # Select and print paths; works over SSH
pdfpick --list --view opened                # List without an interactive terminal
```

Shared search roots live in `home-manager/common.nix` and are installed as
`~/.config/pdfpick/roots`, one home-relative or absolute folder per line.
The package is available on both hosts; the Ghostty launcher, Hyprland shortcut,
and Zathura are desktop configuration. The VPS can use `--print` or `--list`.
Picker opening history lives in `$XDG_STATE_HOME/pdfpick/history.sqlite`
(normally `~/.local/state/pdfpick/history.sqlite`). A private temporary directory
holds paths for the preview while the picker is open and is removed on exit.

**Super+Alt+Z** still opens the latest downloaded PDF directly, and
**Super+Shift+Z** launches Zathura. Rebuild configuration changes with `nxb`.
