# Private companion to the existing Roblox dashboard; no queue or Studio workers.
{ pkgs, ... }:
let
  app = pkgs.callPackage ../pkgs/roblox-opportunities.nix {};
in {
  users.groups.roblox-opportunities = {};
  users.users.roblox-opportunities = {
    isSystemUser = true;
    group = "roblox-opportunities";
    home = "/var/lib/roblox-opportunities";
  };
  systemd.services.roblox-opportunities = {
    description = "Private Roblox Ideas and Trends";
    wantedBy = [ "multi-user.target" ];
    after = [ "network-online.target" ];
    wants = [ "network-online.target" ];
    environment = {
      PYTHONDONTWRITEBYTECODE = "1";
      PYTHONUNBUFFERED = "1";
      SSL_CERT_FILE = "${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt";
    };
    serviceConfig = {
      User = "roblox-opportunities";
      Group = "roblox-opportunities";
      ExecStart = "${app}/bin/roblox-opportunities --port 8786 --state /var/lib/roblox-opportunities";
      WorkingDirectory = "/var/lib/roblox-opportunities";
      StateDirectory = "roblox-opportunities";
      StateDirectoryMode = "0700";
      Restart = "on-failure";
      RestartSec = 3;
      TimeoutStopSec = 15;
      UMask = "0077";
      NoNewPrivileges = true;
      PrivateTmp = true;
      PrivateDevices = true;
      ProtectHome = true;
      ProtectSystem = "strict";
      ProtectKernelTunables = true;
      ProtectControlGroups = true;
      RestrictSUIDSGID = true;
      RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
      MemoryMax = "256M";
    };
  };
}
