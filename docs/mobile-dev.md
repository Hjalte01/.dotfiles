# Mobile Codex Setup

This repo now has two hosts:

- `nixos`: the laptop/desktop config.
- `mobile-dev`: a small VPS config for phone-driven Codex work over Tailscale.

The Home Manager setup is split by role:

- `home-manager/common.nix`: shared terminal tools, Codex, Neovim, tmux, shell defaults.
- `home-manager/home.nix`: desktop-only GUI packages, scripts, services, MIME handlers.
- `home-manager/mobile-dev.nix`: VPS-only shell behavior, currently auto-attaching tmux on SSH.

The intended workflow is:

1. Laptop edits and pushes the dotfiles/repo.
2. VPS runs `tmux`, `codex`, git repos, and long sessions 24/7.
3. Phone uses Termux + Tailscale + SSH, then attaches to the existing tmux session automatically.

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
ssh root@SERVER_IP 'ln -sf /nix/var/nix/profiles/default/bin/* /usr/local/bin/ && nix --version'
nix run github:nix-community/nixos-anywhere -- --phases disko,install,reboot --flake ~/.dotfiles#mobile-dev root@SERVER_IP
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

Install Termux and Tailscale on Android. In Termux:

```sh
pkg install openssh
ssh hjalte@mobile-dev
```

The server shell auto-attaches to `tmux new-session -A -s main` for SSH sessions. Useful short aliases on the VPS:

- `ta`: attach/create the main tmux session.
- `cx`: run `codex`.
- `dots`: go to `~/.dotfiles`.
- `nxb`: rebuild the VPS with `nh os switch ~/.dotfiles#mobile-dev`.
