# dotfiles
Dotfiles to save/share the config files

## Mobile-dev automatic app updates

`nixos/data/queue-deployments.json` is the app deployment registry used by Codex
Queue. It records each repository's Nix revision pin, dedicated services (empty
for static nginx sites), health URLs, and refresh instructions. Entries marked
`none` explicitly have no local hosted app.

After successful queue changes, `codex-queue-deploy.service` updates the relevant
pin, commits it locally, runs `nxb`, and verifies the live app. The timer checks
pending deployment records about every ten seconds; it never calls Codex. The
runner is separate from the queue service and survives its restart during NixOS
activation. Failed updates show a deployment log and a retry button in the queue.

Add new hosted apps in the mobile-dev modules and this registry, then run `nxb`.
Do not add arbitrary prompt-supplied commands to the registry. Git pushing remains
an explicit queue review action; local deployment does not require pushing first.
