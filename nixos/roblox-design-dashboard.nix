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
  # Images run under the existing signed-in identity and serialized Codex queue.
  systemd.services.roblox-design-worker = let
    queue = pkgs.callPackage ../pkgs/codex-queue.nix {};
    python = pkgs.python3.withPackages (p: [ p.flask p.pywebpush p.cryptography ]);
    workerConfig = pkgs.writeText "roblox-design-worker.json" (builtins.toJSON {
      games = [ "resonance_lab" ];
      resources = [ "codex:serial" ];
      timeoutSeconds = 86400;
      commands.generate = [ "${python}/bin/python3" "-B" "${dashboard}/share/roblox-design-dashboard/website/codex_queue_adapter.py" ];
    });
  in {
    description = "Roblox design image worker using the existing Codex queue";
    wantedBy = [ "multi-user.target" ];
    after = [ "roblox-design-dashboard.service" "codex-queue.service" ];
    wants = [ "roblox-design-dashboard.service" "codex-queue.service" ];
    environment = {
      PYTHONUNBUFFERED = "1";
      PYTHONDONTWRITEBYTECODE = "1";
      PYTHONPATH = "${queue}/${pkgs.python3.sitePackages}";
      CODEX_HOME = "/home/hjalte/.codex";
      DASHBOARD_QUEUE_DB = "/var/lib/codex-queue/queue.sqlite3";
      DASHBOARD_QUEUE_REPOSITORY = "/home/hjalte/documents/roblox-gamemodes";
      DASHBOARD_QUEUE_LINKS = "/var/lib/roblox-design-worker/queue-links";
      DASHBOARD_GENERATED_IMAGES = "/home/hjalte/.codex/generated_images";
    };
    serviceConfig = {
      User = "hjalte";
      Group = "users";
      ExecStart = "${python}/bin/python3 -B ${dashboard}/share/roblox-design-dashboard/website/worker.py --server http://127.0.0.1:8765/roblox-design --config ${workerConfig} --worker-id mobile-dev-design --work-dir /var/lib/roblox-design-worker/jobs";
      StateDirectory = "roblox-design-worker";
      StateDirectoryMode = "0700";
      WorkingDirectory = "/var/lib/roblox-design-worker";
      EnvironmentFile = "/var/lib/roblox-design-dashboard/worker.env";
      Restart = "on-failure";
      RestartSec = 5;
      UMask = "0077";
      NoNewPrivileges = true;
      PrivateTmp = true;
      PrivateDevices = true;
      ProtectHome = "read-only";
      ProtectSystem = "strict";
      ReadWritePaths = [ "/var/lib/codex-queue" "/var/lib/roblox-design-worker" ];
      ProtectKernelTunables = true;
      ProtectControlGroups = true;
      RestrictSUIDSGID = true;
      RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
      MemoryMax = "256M";
    };
  };
}
