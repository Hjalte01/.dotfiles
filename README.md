# dotfiles
Dotfiles to save/share the config files

Focus a Firefox upload input, then use **Super+Alt+F** (`filepick`), select files,
and press **Enter** to attach them automatically. Press `Esc`, then `d` to drag
instead. **Super+Alt+D** reopens the last selection for dragging.
See [Filepick keys and usage](docs/filepick.md).

Use **Super+Ctrl+Z** (`pdfpick`) to fuzzy-find PDFs and open them in Zathura.
Switch between all PDFs, recent downloads, and recent opens; filter by folder
and preview paper text. See [PDF picker keys and usage](docs/pdfpick.md).

Hold **Super** to see shortcuts. **Super+Esc** pins the Rust key map: `/` searches
keys and descriptions, `?` shows help. Groups: **Super+G** websites, **Super+A**
audio, **Super+X** pointer tools, **Super+T** desktop, **Super+C** Codex.
See [Desktop key map and moved shortcuts](docs/desktop-which-key-prd.md).

Choose a shared app theme with **Super+T → C**, a wallpaper with **Super+T → W**,
or cycle matching wallpapers with **Super+T → V**. Six palettes include 18 original
4K backgrounds. See [Themes and wallpapers](docs/themes.md).

## Mobile-dev automatic app updates

`nixos/data/queue-deployments.json` is the app deployment registry used by Codex
Queue. It records each repository's Nix revision pin, dedicated services (empty
for static nginx sites), health URLs, and refresh instructions. Entries marked
`none` explicitly have no local hosted app.

After successful queue changes, `codex-queue-deploy.service` updates the relevant
pin, commits it locally, runs `nxb`, and verifies the live app. A systemd path unit wakes the runner immediately after a deployment request;
the timer checks pending and temporarily blocked deployments every ten seconds as fallback; it never calls Codex. The
runner is separate from the queue service and survives its restart during NixOS
activation. Blocked or failed updates hold subsequent prompts and show a visible banner,
deployment log, retry, and Continue without deploying controls. Dirty worktrees
recover automatically after their edits are committed; builds require explicit retry.
Version IDs in the registry are checked against `/app-versions.json`; Codex Queue
also exposes its process revision at `/codex/healthz`. The hub offers a refresh
button when the page or shared navigation has a newer live revision.

Add new hosted apps in the mobile-dev modules and this registry, then run `nxb`.
Do not add arbitrary prompt-supplied commands to the registry. Git pushing remains
an explicit queue review action; local deployment does not require pushing first.
