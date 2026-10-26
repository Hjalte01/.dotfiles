# VPS-only visual reviews. Studio and provider workers remain separate.
{ pkgs, ... }:
let
  dashboard = pkgs.callPackage ../pkgs/roblox-design-dashboard.nix {};
  source = "/srv/roblox-design-source";
in {
  users.groups.roblox-design-dashboard = {};
  users.users.roblox-design-dashboard = {
    isSystemUser = true;
    group = "roblox-design-dashboard";
    home = "/var/lib/roblox-design-dashboard";
  };
  systemd.tmpfiles.rules = [
    "d ${source} 0755 root root -"
  ];
  systemd.services.roblox-design-dashboard = {
    description = "Private Roblox visual design reviews";
    wantedBy = [ "multi-user.target" ];
    after = [ "network.target" ];
    path = [ pkgs.git ];
    environment = {
      PYTHONDONTWRITEBYTECODE = "1";
      PYTHONUNBUFFERED = "1";
      DASHBOARD_REPO = source;
      DASHBOARD_STATE = "/var/lib/roblox-design-dashboard";
      CAPTURE_ROOT = "/var/lib/roblox-design-dashboard/gallery/current";
      DASHBOARD_HOST = "127.0.0.1";
      DASHBOARD_PORT = "8765";
      DASHBOARD_BASE_PATH = "/roblox-design";
      DASHBOARD_ALLOWED_HOSTS = "mobile-dev.tail55f864.ts.net,mobile-dev";
      DASHBOARD_REVISION = dashboard.src.rev;
      GIT_OPTIONAL_LOCKS = "0";
      GIT_CONFIG_COUNT = "1";
      GIT_CONFIG_KEY_0 = "safe.directory";
      GIT_CONFIG_VALUE_0 = source;
    };
    serviceConfig = {
      User = "roblox-design-dashboard";
      Group = "roblox-design-dashboard";
      ExecStart = "${dashboard}/bin/roblox-design-dashboard";
      WorkingDirectory = "/var/lib/roblox-design-dashboard";
      StateDirectory = "roblox-design-dashboard";
      StateDirectoryMode = "0700";
      EnvironmentFile = "-/var/lib/roblox-design-dashboard/worker.env";
      Restart = "on-failure";
      RestartSec = 3;
      UMask = "0077";
      NoNewPrivileges = true;
      PrivateTmp = true;
      PrivateDevices = true;
      ProtectHome = true;
      ProtectSystem = "strict";
      # Preserve the actual Git source identity, mounted read-only despite ProtectHome.
      BindReadOnlyPaths = [ "/home/hjalte/documents/roblox-gamemodes:${source}" ];
      ProtectKernelTunables = true;
      ProtectControlGroups = true;
      RestrictSUIDSGID = true;
      RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
      MemoryMax = "768M";
    };
  };
}
