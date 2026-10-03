# dotfiles
Dotfiles to save/share the config files

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
