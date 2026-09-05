# Mobile Codex Setup

This repo now has two hosts:

- `nixos`: the laptop/desktop config.
- `mobile-dev`: a small VPS config for phone-driven Codex work over Tailscale.

The Home Manager setup is split by role:

- `home-manager/common.nix`: shared terminal tools, Codex, Neovim, tmux, shell defaults.
- `home-manager/home.nix`: desktop-only GUI packages, scripts, services, MIME handlers.
- `home-manager/mobile-dev.nix`: VPS-only shell behavior, currently auto-attaching tmux on SSH.

The Bash setup is split the same way:

- `bash/common.sh`: shared aliases/functions for Codex, rebuilds, editors, history, tmux, and portable clipboard workflows.
- `bash/desktop.sh`: desktop-only GUI, hardware, network, media, and legacy rebuild helpers.
- `bash/mobile-dev.sh`: VPS-only terminal normalization and tmux auto-attach.
- `bash/.mybashrc.sh`: compatibility loader for older habits.

The intended workflow is:

1. Laptop edits and pushes the dotfiles/repo.
2. VPS runs `tmux`, `codex`, git repos, and long sessions 24/7.
3. Phone uses Tailscale + an SSH client, then attaches to the existing tmux session automatically.

## Laptop

Rebuild the laptop so it joins the tailnet and accepts key-only SSH:

```sh
nh os switch ~/.dotfiles#nixos
sudo tailscale up
```

## VPS Install

Create a cheap x86_64 VPS, for example Hetzner Cloud in Germany or Finland. Boot its default Linux image and make sure your SSH key can log in as `root`.

Check the VPS disk path before installing:

```sh
ssh root@SERVER_IP lsblk
```

`mobile-dev` currently assumes `/dev/sda`. If the boot disk is different, update `disko.devices.disk.main.device` in `nixos/mobile-dev.nix`.

Install NixOS from this flake:

```sh
nix run github:nix-community/nixos-anywhere -- --flake ~/.dotfiles#mobile-dev root@SERVER_IP
```

If Hetzner's default image fails during the kexec step, enable the Hetzner Rescue System, power cycle the server, then run the install from rescue:

```sh
ssh-keygen -R SERVER_IP
ssh root@SERVER_IP lsblk
ssh root@SERVER_IP 'curl -L https://nixos.org/nix/install | sh -s -- --daemon --yes'
./scripts/install-mobile-dev-vps SERVER_IP
```

After reboot:

```sh
ssh hjalte@SERVER_IP
sudo tailscale up --ssh
```

Once Tailscale is connected, prefer the Tailscale name/IP from your phone:

```sh
ssh hjalte@mobile-dev
```

## Phone

On iOS, install Tailscale and an SSH client such as Termius. Connect the phone to the same tailnet, then create an SSH host:

- Host: `mobile-dev`, or the server's `100.x.y.z` Tailscale IP.
- Port: `22`.
- Username: `hjalte`.
- Authentication: Tailscale SSH can work without a separate phone SSH key. For normal OpenSSH, add a phone-specific public key to `nixos/mobile-dev.nix`.

On Android, install Tailscale and Termux. In Termux:

```sh
pkg install openssh
ssh hjalte@mobile-dev
```

The server shell auto-attaches to `tmux new-session -A -s main` for SSH sessions. The main workflow commands are shared by both hosts:

- `ta`: attach/create the main tmux session.
- `codex` / `cx`: run Codex with `--yolo` by default; pass `--no-yolo` to use the configured permissions instead.
- `dots`: go to `~/.dotfiles`.
- `cd.`: go to `~/.dotfiles`.
- `nxb`: rebuild the active host (`nixos` or `mobile-dev`) with `nh`.
- `conf` / `home`: edit the active host's NixOS or Home Manager module.
- `brc.`: reload the shared Bash configuration and the active host's Bash file.
- `nvimconf` / `nvimkeyb`: edit the shared Neovim configuration or keymaps.
- `history` (or Ctrl-H): select shell history with `fzf` and copy the selection.
- `sharecode` / `sharetree`: copy a Repomix snapshot or repository tree without creating an output file.
- `p` / `v`: print the Wayland clipboard locally or the tmux paste buffer over remote SSH.

Docker is enabled for both NixOS hosts through the shared module in `flake.nix`, and `hjalte` is a member of the `docker` group so Docker commands do not require `sudo`.

## Private web hub

The tailnet-only landing page is `https://mobile-dev.tail55f864.ts.net/`.
Tailscale Serve terminates trusted HTTPS and forwards it to Nginx on
`127.0.0.1:8080`; Nginx serves the static hub and Game Factory build and proxies
`/codex/` to Codex Queue on `127.0.0.1:8787`. Only SSH is allowed through the
public firewall. Enable HTTPS certificates once in the Tailscale DNS admin page
before the first activation.

If Serve has not been enabled yet, `tailscale-serve-vps-hub.service` times out
quickly and its systemd timer retries once per minute without blocking a system
rebuild. After enabling it, inspect `systemctl status
tailscale-serve-vps-hub` and `tailscale serve status` to confirm the HTTPS
forwarding was applied.

Application source is committed in `vps-hub`, `game_factory`, and
`codex-queue`, then pinned by full commit revision in `pkgs/`. To deploy an
update, push the application commit, update the corresponding pin (and npm hash
when Game Factory dependencies change), run a full flake build, and use `nxb`.
The hub repository documents the coordinated manifest, package/service, proxy,
and health-route steps for adding, disabling, or removing a hosted site.

The shared `c`, `cmdc`, `sharecode`, `sharetree`, and history helpers use the Wayland clipboard locally. In a remote tmux session they update both tmux's paste buffer and the client clipboard through OSC52; OSC52 client support depends on the phone's SSH app. Consequently, remote `p` and `v` print tmux's buffer rather than attempting to read the phone OS clipboard. Outside Wayland and remote tmux, copying still emits OSC52, while paste reports that the environment is unsupported.

## Git On VPS

Set the Git identity once:

```sh
git config --global user.name "YOUR_GIT_NAME"
git config --global user.email "YOUR_GIT_EMAIL"
```

Prefer SSH remotes for GitHub. If `git pull` asks for a username/password, switch the remote to SSH and add a VPS-specific public key to GitHub:

```sh
cd ~/.dotfiles
git remote -v
ssh-keygen -t ed25519 -C "mobile-dev"
cat ~/.ssh/id_ed25519.pub
```

Then add the printed public key in GitHub under SSH keys and test:

```sh
ssh -T git@github.com
git pull
```
