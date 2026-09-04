{
  config,
  lib,
  pkgs,
  ...
}: let
  webdavUser = "obsidian-webdav";
  webdavData = "/srv/obsidian-webdav";
  webdavSecrets = "/var/lib/obsidian-webdav-secrets";
  resticRepository = "/var/lib/obsidian-restic";
  resticSecrets = "/var/lib/obsidian-restic-secrets";
  resticEnvironment = {
    RESTIC_CACHE_DIR = "/var/cache/obsidian-restic";
    RESTIC_REPOSITORY = resticRepository;
    RESTIC_PASSWORD_FILE = "${resticSecrets}/repository-password";
  };
in {
  users.groups.${webdavUser} = {};
  users.users.${webdavUser} = {
    isSystemUser = true;
    group = webdavUser;
    home = "/var/empty";
    createHome = false;
    shell = pkgs.shadow;
  };

  systemd.tmpfiles.rules = [
    "d ${webdavData} 0700 ${webdavUser} ${webdavUser} -"
    "d ${webdavSecrets} 0710 root ${webdavUser} -"
    "d ${resticRepository} 0700 root root -"
    "d ${resticSecrets} 0700 root root -"
    "L+ /root/README-obsidian-sync.md - - - - /etc/obsidian-webdav/README.md"
  ];

  systemd.services.obsidian-webdav-prepare = {
    description = "Prepare credentials for Obsidian WebDAV";
    requiredBy = ["obsidian-webdav.service"];
    before = ["obsidian-webdav.service"];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      UMask = "0077";
    };
    path = [pkgs.apacheHttpd pkgs.coreutils pkgs.openssl];
    script = ''
      install -d -m 0710 -o root -g ${webdavUser} ${webdavSecrets}
      if [[ ! -s ${webdavSecrets}/password ]]; then
        openssl rand -hex 32 > ${webdavSecrets}/password
        chmod 0400 ${webdavSecrets}/password
      fi

      htpasswd -Bbn ${webdavUser} "$(cat ${webdavSecrets}/password)" > ${webdavSecrets}/htpasswd.new
      install -m 0400 -o ${webdavUser} -g ${webdavUser} \
        ${webdavSecrets}/htpasswd.new ${webdavSecrets}/htpasswd
      rm -f ${webdavSecrets}/htpasswd.new
    '';
  };

  systemd.services.obsidian-webdav = {
    description = "Obsidian WebDAV storage backend";
    wantedBy = ["multi-user.target"];
    after = ["network.target"];
    requires = ["obsidian-webdav-prepare.service"];
    serviceConfig = {
      Type = "simple";
      User = webdavUser;
      Group = webdavUser;
      ExecStart = lib.concatStringsSep " " [
        (lib.getExe pkgs.rclone)
        "serve webdav"
        webdavData
        "--addr 127.0.0.1:8686"
        "--baseurl /obsidian"
        "--htpasswd ${webdavSecrets}/htpasswd"
        "--config /dev/null"
        "--no-modtime"
      ];
      Restart = "on-failure";
      RestartSec = "5s";
      UMask = "0077";

      NoNewPrivileges = true;
      PrivateDevices = true;
      PrivateTmp = true;
      ProtectClock = true;
      ProtectControlGroups = true;
      ProtectHome = true;
      ProtectHostname = true;
      ProtectKernelLogs = true;
      ProtectKernelModules = true;
      ProtectKernelTunables = true;
      ProtectProc = "invisible";
      ProtectSystem = "strict";
      ReadOnlyPaths = ["${webdavSecrets}/htpasswd"];
      ReadWritePaths = [webdavData];
      RemoveIPC = true;
      RestrictAddressFamilies = ["AF_UNIX" "AF_INET"];
      RestrictNamespaces = true;
      RestrictRealtime = true;
      RestrictSUIDSGID = true;
      SystemCallArchitectures = "native";
      LockPersonality = true;
      CapabilityBoundingSet = "";
    };
  };

  systemd.services.obsidian-backup-init = {
    description = "Initialize the encrypted Obsidian restic repository";
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      UMask = "0077";
    };
    environment = resticEnvironment;
    path = [pkgs.coreutils pkgs.openssl pkgs.restic];
    script = ''
      install -d -m 0700 -o root -g root ${resticRepository} ${resticSecrets}
      if [[ ! -s ${resticSecrets}/repository-password ]]; then
        openssl rand -hex 32 > ${resticSecrets}/repository-password
        chmod 0400 ${resticSecrets}/repository-password
      fi
      if [[ ! -f ${resticRepository}/config ]]; then
        restic init
      fi
    '';
  };

  systemd.services.obsidian-backup = {
    description = "Versioned backup of Obsidian WebDAV storage";
    requires = ["obsidian-backup-init.service"];
    after = ["obsidian-backup-init.service"];
    environment = resticEnvironment;
    path = [pkgs.restic];
    serviceConfig = {
      Type = "oneshot";
      CacheDirectory = "obsidian-restic";
      CacheDirectoryMode = "0700";
      UMask = "0077";
      NoNewPrivileges = true;
      PrivateDevices = true;
      PrivateTmp = true;
      ProtectClock = true;
      ProtectControlGroups = true;
      ProtectHome = true;
      ProtectHostname = true;
      ProtectKernelLogs = true;
      ProtectKernelModules = true;
      ProtectKernelTunables = true;
      ProtectProc = "invisible";
      ProtectSystem = "strict";
      ReadOnlyPaths = [webdavData "${resticSecrets}/repository-password"];
      ReadWritePaths = [resticRepository];
      RemoveIPC = true;
      RestrictAddressFamilies = ["AF_UNIX" "AF_INET" "AF_INET6"];
      RestrictNamespaces = true;
      RestrictRealtime = true;
      RestrictSUIDSGID = true;
      SystemCallArchitectures = "native";
      LockPersonality = true;
      # The vault is deliberately mode 0700 under the WebDAV account. Keep
      # root's DAC override so this backup-only unit can read it.
      CapabilityBoundingSet = ["CAP_DAC_OVERRIDE"];
    };
    script = ''
      restic backup ${webdavData} --tag obsidian-webdav
      restic forget \
        --tag obsidian-webdav \
        --keep-last 12 \
        --keep-daily 30 \
        --keep-weekly 8 \
        --keep-monthly 12 \
        --prune
    '';
  };

  systemd.timers.obsidian-backup = {
    description = "Back up Obsidian WebDAV storage every six hours";
    wantedBy = ["timers.target"];
    timerConfig = {
      OnCalendar = "*-*-* 00/6:00:00";
      Persistent = true;
      RandomizedDelaySec = "10m";
      Unit = "obsidian-backup.service";
    };
  };

  environment.systemPackages = [pkgs.rclone pkgs.restic];

  environment.etc."obsidian-webdav/README.md".text = ''
    # Obsidian study vault synchronization

    ## Architecture

    The iPad and laptop each keep a complete local `study` vault. Remotely Save
    synchronizes those local vaults with this server; the server is not mounted as
    either device's filesystem.

    `Remotely Save -> Tailscale HTTPS -> nginx -> rclone WebDAV (loopback only)`

    Data is stored at `${webdavData}/`, owned by the unprivileged
    `${webdavUser}` account with mode 0700. The remote is intentionally empty
    until the iPad performs the initial synchronization.

    ## WebDAV administration

    - URL: `https://mobile-dev.tail55f864.ts.net/obsidian/`
    - Username: `${webdavUser}`
    - Service: `obsidian-webdav.service`
    - Status: `sudo systemctl status obsidian-webdav`
    - Restart: `sudo systemctl restart obsidian-webdav`
    - NixOS module: `/home/hjalte/.dotfiles/nixos/obsidian-webdav.nix`
    - nginx configuration: `/home/hjalte/.dotfiles/nixos/mobile-dev.nix`
    - nginx service: `nginx.service`
    - Tailscale HTTPS service: `tailscale-serve-vps-hub.service`

    The plaintext WebDAV password is root-readable only at
    `${webdavSecrets}/password` and is deliberately not included here. To change
    it, replace that file atomically with a new mode-0400 root-owned password,
    then run:

        sudo systemctl restart obsidian-webdav-prepare obsidian-webdav

    ## Versioned backups

    The encrypted local restic repository is `${resticRepository}/`. It is not
    below any web root and is not served by nginx. `obsidian-backup.timer` runs at
    00:00, 06:00, 12:00, and 18:00 (with up to ten minutes of jitter). Retention
    is 12 most recent, 30 daily, 8 weekly, and 12 monthly snapshots.

    Status and manual backup:

        sudo systemctl status obsidian-backup.timer
        sudo systemctl start obsidian-backup.service

    List snapshots:

        sudo env RESTIC_REPOSITORY=${resticRepository} \
          RESTIC_PASSWORD_FILE=${resticSecrets}/repository-password \
          restic snapshots --tag obsidian-webdav

    Restore one file to a safe staging directory (replace SNAPSHOT and path):

        sudo install -d -m 0700 /srv/obsidian-restore
        sudo env RESTIC_REPOSITORY=${resticRepository} \
          RESTIC_PASSWORD_FILE=${resticSecrets}/repository-password \
          restic restore SNAPSHOT --target /srv/obsidian-restore \
          --include /srv/obsidian-webdav/path/to/file.md

    Restore the full vault to a safe staging directory:

        sudo install -d -m 0700 /srv/obsidian-restore
        sudo env RESTIC_REPOSITORY=${resticRepository} \
          RESTIC_PASSWORD_FILE=${resticSecrets}/repository-password \
          restic restore latest --tag obsidian-webdav --target /srv/obsidian-restore

    Inspect staged data before copying anything back into the live directory.

    ## Offsite status

    Local versioned backup configured; no independent offsite backup exists yet.
    The encrypted repository resides on the same VPS and protects against
    synchronized deletion/corruption, but not complete VPS loss.
  '';
}
