{
  config,
  lib,
  modulesPath,
  pkgs,
  ...
}: let
  codex = pkgs.callPackage ../pkgs/codex-cli.nix {};
  codexQueue = pkgs.callPackage ../pkgs/codex-queue.nix {};
in {
  imports = [
    "${modulesPath}/profiles/qemu-guest.nix"
  ];

  nix.settings.experimental-features = ["nix-command" "flakes"];
  nixpkgs.config.allowUnfree = true;

  networking.hostName = "mobile-dev";
  networking.useDHCP = lib.mkDefault true;

  time.timeZone = "Europe/Copenhagen";
  i18n.defaultLocale = "en_DK.UTF-8";

  boot.loader.grub = {
    enable = true;
    efiSupport = true;
    efiInstallAsRemovable = true;
    device = "nodev";
  };

  disko.devices = {
    disk.main = {
      type = "disk";
      # Hetzner Cloud usually exposes the boot disk as /dev/sda.
      # Change this before installing if your provider uses another path.
      device = "/dev/sda";
      content = {
        type = "gpt";
        partitions = {
          boot = {
            size = "1M";
            type = "EF02";
          };
          ESP = {
            size = "512M";
            type = "EF00";
            content = {
              type = "filesystem";
              format = "vfat";
              mountpoint = "/boot";
              mountOptions = ["umask=0077"];
            };
          };
          root = {
            size = "100%";
            content = {
              type = "filesystem";
              format = "ext4";
              mountpoint = "/";
            };
          };
        };
      };
    };
  };

  users.users.hjalte = {
    isNormalUser = true;
    description = "Hjalte";
    extraGroups = ["wheel"];
    openssh.authorizedKeys.keys = [
      "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGFobE7CbB7HXxan6i+xkDc6p7m6MZwoRjRA7CBFYsq0 hjalte@bjoernstrup.net"
    ];
  };

  security.sudo.wheelNeedsPassword = false;

  services.openssh = {
    enable = true;
    settings = {
      PasswordAuthentication = false;
      KbdInteractiveAuthentication = false;
      PermitRootLogin = "prohibit-password";
    };
  };

  services.tailscale.enable = true;
  services.cron.enable = true;

  networking.firewall = {
    enable = true;
    # Codex Queue listens on 8787, but tailscale0 is the only trusted interface.
    # Deliberately keep 8787 out of the public port allowlist.
    trustedInterfaces = ["tailscale0"];
    allowedTCPPorts = [22];
  };

  systemd.services.codex-queue = {
    description = "Tailnet dashboard for unattended Codex tasks";
    wantedBy = ["multi-user.target"];
    after = ["network-online.target" "tailscaled.service"];
    wants = ["network-online.target"];
    path = with pkgs; [
      bash
      bubblewrap
      coreutils
      curl
      findutils
      git
      gnugrep
      gnused
      jq
      nix
      nodejs_22
      python3
      ripgrep
    ];

    environment = {
      CODEX_HOME = "/home/hjalte/.codex";
      CODEX_QUEUE_CODEX = lib.getExe' codex "codex";
      CODEX_QUEUE_HOST = "0.0.0.0";
      CODEX_QUEUE_PORT = "8787";
      CODEX_QUEUE_STATE_DIR = "/var/lib/codex-queue";
      HOME = "/home/hjalte";
    };

    serviceConfig = {
      Type = "simple";
      User = "hjalte";
      Group = "users";
      ExecStart = lib.getExe codexQueue;
      Restart = "on-failure";
      RestartSec = 5;
      StateDirectory = "codex-queue";
      StateDirectoryMode = "0700";
      WorkingDirectory = "/var/lib/codex-queue";

      # Codex Queue discovers current and future Git worktrees beneath the home
      # directory. Codex's workspace sandbox still restricts each run to the
      # repository selected for that task.
      ProtectSystem = "strict";
      ProtectHome = "read-only";
      ReadWritePaths = [
        "/var/lib/codex-queue"
        "/home/hjalte"
      ];
      PrivateTmp = true;
      PrivateDevices = true;
      NoNewPrivileges = true;
      CapabilityBoundingSet = "";
      RemoveIPC = true;
      ProtectClock = true;
      ProtectControlGroups = true;
      ProtectHostname = true;
      ProtectKernelLogs = true;
      ProtectKernelModules = true;
      ProtectKernelTunables = true;
      ProtectProc = "invisible";
      RestrictAddressFamilies = ["AF_UNIX" "AF_INET" "AF_INET6"];
      RestrictNamespaces = false; # Codex's workspace sandbox uses user/mount namespaces.
      RestrictRealtime = true;
      RestrictSUIDSGID = true;
      SystemCallArchitectures = "native";
      LockPersonality = true;
      UMask = "0077";
    };
  };

  environment.systemPackages = with pkgs; [
    cacert
    git
    python3
    tailscale
    vim
    codexQueue
  ];

  system.stateVersion = "25.11";
}
