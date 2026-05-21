# Mobile Codex Setup

This repo now has two hosts:

- `nixos`: the laptop/desktop config.
- `mobile-dev`: a small VPS config for phone-driven Codex work over Tailscale.

The Home Manager setup is split by role:

- `home-manager/common.nix`: shared terminal tools, Codex, Neovim, tmux, shell defaults.
- `home-manager/home.nix`: desktop-only GUI packages, scripts, services, MIME handlers.
- `home-manager/mobile-dev.nix`: VPS-only shell behavior, currently auto-attaching tmux on SSH.

The Bash setup is split the same way:

- `bash/common.sh`: shared aliases/functions such as `..`, `cd.`, `cmdc`, `c`, `cx`, `ta`, and `cdd`.
- `bash/desktop.sh`: desktop-only clipboard, project, media, and desktop rebuild helpers.
- `bash/mobile-dev.sh`: VPS-only terminal normalization, tmux auto-attach, and mobile-dev rebuild helper.
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

The server shell auto-attaches to `tmux new-session -A -s main` for SSH sessions. Useful short aliases on the VPS:

- `ta`: attach/create the main tmux session.
- `cx`: run `codex`.
- `dots`: go to `~/.dotfiles`.
- `cd.`: go to `~/.dotfiles`.
- `nxb`: rebuild the VPS with `sudo nixos-rebuild switch --flake ~/.dotfiles#mobile-dev`.

The shared `c` and `cmdc` helpers use Wayland clipboard locally when available, otherwise OSC52 escape sequences. OSC52 is enabled through tmux with `set-clipboard` and `allow-passthrough`, so remote copies may reach the local terminal clipboard if the phone SSH client supports OSC52.

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
