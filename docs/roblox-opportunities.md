# Roblox Ideas & Trends on mobile-dev

Requested and deployed from the main PC on 11 November 2026. This is a private
companion to the existing Roblox Studio/design dashboard, with no Studio or
Codex workers of its own.

- URL: https://mobile-dev.tail55f864.ts.net/roblox-opportunities/
- Service: `roblox-opportunities.service`, enabled through `multi-user.target`,
  restart on failure, dedicated `roblox-opportunities` account.
- Code: immutable Nix package, `pkgs/roblox-opportunities.nix`.
- State: `/var/lib/roblox-opportunities/board.sqlite3`, mode 0700 parent and
  private files; includes ordered ideas, edits, revision and market snapshots.
- Proxy: existing Tailscale Serve HTTPS -> loopback nginx -> `127.0.0.1:8786`.
  The prefix is stripped and Host preserved for same-origin writes. No public
  firewall port or SSH tunnel is required.
- Hub card and Switch apps entry: `roblox-opportunities`, in the separately
  pinned `vps-hub` source.

## Release source and updates

Original supplied release: `roblox-opportunities.tar.gz`, containing the bundled
installer and Hero Draft (`auction`) with `art/auction-{1,2,3}.webp`. The installer
is retained as input but is not run: systemd and nginx are managed by NixOS.

Archive SHA256:
`55809bd5303f9991290fcfd3710c71917d6dbb818d1da9882b5424e0d5a54683`.
Retained on the VPS at
`/srv/roblox-opportunities/releases/55809bd5303f9991290fcfd3710c71917d6dbb818d1da9882b5424e0d5a54683.tar.gz`
and `/home/hjalte/roblox-opportunities.tar.gz`. The package verifies the extracted source NAR hash
before importing it into the Nix store. Back up this original archive
with the dotfiles to reproduce the deployment on a replacement host. The PC
original is in `/home/hjalte/Documents/ChatGPT/roblox gamemodes/`.

The reviewed patch under `pkgs/roblox-opportunities/` adapts Roblox's current
`sortDisplayName` and stable chart IDs, retains actual chart filters, keeps
comparisons within matching chart/filter scope, and adds a cheap database health
endpoint. Python regression checks run as part of the package build.

For future source updates, retain the new archive under a new digest filename,
review the source and patch, update the package source/hash, then build and run
`nxb` through the established serialized VPS activation workflow. Use
`/var/lib/codex-queue/deployment.lock`; do not overlap the deployment runner.
Do not overwrite or remove the SQLite directory. No new source repository or
automatic chart-refresh timer is created by this deployment.

## Preservation and recovery

No prior preview/service `board.sqlite3` was found in the conventional home,
state, `/srv` or `/var/lib` locations during initial inspection. Startup uses
`CREATE TABLE IF NOT EXISTS` and `INSERT OR IGNORE`, preserving any existing
board rather than reseeding it. A future older board may lack newly supplied
ideas; merge missing ideas deliberately, preserving edits and ranking.

For a consistent online backup use Python's `sqlite3.Connection.backup` as root
or the service account, or stop only this service before copying the database.
Restore with the service stopped, retaining its account ownership and mode 0600.
Never replace a current database with a seed to repair an upstream error.
Failed Roblox refreshes do not delete snapshots. The supplied historical market
sample remains available alongside live snapshots; it is not a current chart.

## Operations and verification

```sh
systemctl status roblox-opportunities --no-pager
systemctl is-enabled roblox-opportunities
curl --fail http://127.0.0.1:8786/api/health
journalctl -u roblox-opportunities -n 50 --no-pager
```

Open the private URL from a tailnet device. Verify Idea Board, Hero Draft's
three images, Market Research and a saved live chart. For persistence testing,
restart only `roblox-opportunities`, then compare the board and snapshots before
and after. Check the hub `/` and existing dashboard `/roblox/api/health`.
Full VPS reboot and unrelated service restarts are unnecessary.

Verified on 11 November 2026 through the private HTTPS URL from the main PC:

- Both Idea board and Market research HTML, JavaScript/CSS, board API and hub
  app-list entry respond successfully. All eleven ideas are present.
- Hero Draft has three references; all three WebP responses match original
  archive bytes and have image/webp content types.
- Same-origin save succeeds with unchanged idea contents/order (revision 0 -> 1).
- A real VPS Top Trending refresh saved 98 experiences at
  `2026-11-11T14:20:05.048006+00:00`, filters
  `device=computer,age=all,country=de`. CCU is global; chart placement uses those
  returned discovery filters. SQLite contains that snapshot, and its historical
  seed remains selectable too.
- Restarting only the new service preserves the complete board API payload,
  including revision, ordered ideas and snapshots, byte-for-byte as JSON data.
  SQLite quick_check is ok; directory mode 0700 and database mode 0600 confirmed.
- Boot target link, is-enabled, Restart=on-failure and loopback binding confirmed.
- Existing hub and Roblox dashboard HTML and health API respond; the existing
  dashboard process was not restarted. Tailscale Serve remains tailnet-only.
- Full NixOS nxb activation succeeds, including package checks (8 Python tests,
  2 JavaScript tests and JavaScript syntax) and nginx configuration validation.
- A consistent deployment backup passed quick_check at
  `/var/backups/roblox-opportunities/board-20261111-deployment.sqlite3` (root-only).

Browser UI automation was unavailable (empty browser inventory), so these are
HTTP/API, file-provenance, service and database checks, not visual UI approval.
No deployment or Roblox-upstream blocker remains. The API schema mismatch,
SQLite connection cleanup, pure archive import and nginx Host-header validation
issues found during preparation were repaired and the affected checks passed.
Private verification JSON and snapshots are retained on the PC under
`~/.local/state/roblox-opportunities-deploy/20261111/`; build logs are on the VPS
under `~/.local/state/roblox-opportunities-nxb-20261111*.log`.
