{
  config,
  lib,
  modulesPath,
  pkgs,
  ...
}: {
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
    trustedInterfaces = ["tailscale0"];
    allowedTCPPorts = [22];
  };

  environment.systemPackages = with pkgs; [
    cacert
    git
    python3
    tailscale
    vim
  ];

  system.stateVersion = "25.11";
}
