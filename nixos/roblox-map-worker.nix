# Map jobs use the same serial Queue, allowance gate and approved source cache.
{ pkgs, ... }:
let
  dashboard = pkgs.callPackage ../pkgs/roblox-design-dashboard.nix {};
  asset = pkgs.callPackage ../pkgs/roblox-asset-studio.nix {};
  queue = pkgs.callPackage ../pkgs/codex-queue.nix {};
  devices = import ../pkgs/devices.nix { inherit pkgs; };
  state = "/var/lib/roblox-asset-studio";
  repository = "/home/hjalte/documents/roblox-gamemodes";
  source = "/srv/roblox-map-source";
  readiness = pkgs.writeText "roblox-map-worker-ready.py" ''
    import json,time,urllib.request,urllib.error
    for attempt in range(45):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8765/roblox/api/health", timeout=1) as response:
                value = json.loads(response.read(8192))
            if value.get("ok") is True and value.get("revision") == "${dashboard.src.rev}":
                break
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(.5)
    else:
        raise SystemExit("Roblox Studio coordinator is not ready at its pinned revision.")
  '';
in {
  systemd.tmpfiles.rules = [ "d ${source} 0755 root root -" ];
  systemd.services.roblox-map-worker = {
    description = "Resumable Roblox map planning and generation";
    wantedBy = [ "multi-user.target" ];
    after = [ "roblox-design-dashboard.service" "codex-queue.service" ];
    wants = [ "roblox-design-dashboard.service" "codex-queue.service" ];
    path = [ dashboard.python pkgs.nodejs_22 pkgs.git pkgs.coreutils pkgs.ripgrep devices ];
    environment = {
      PYTHONDONTWRITEBYTECODE = "1";
      PYTHONUNBUFFERED = "1";
      PYTHONPATH = "${queue}/${pkgs.python3.sitePackages}";
      CODEX_HOME = "/home/hjalte/.codex";
      XDG_STATE_HOME = "${state}/map-device-state";
      CODEX_QUEUE_ASSET_ROOT = "${state}/jobs";
      ASSET_STUDIO_REFERENCE_HELPER = "${asset}/share/roblox-asset-studio/website/asset_tools/reference_set.py";
      ASSET_STUDIO_TOOLKIT = "${asset.toolkit}";
    };
    serviceConfig = {
      User = "hjalte";
      Group = "users";
      WorkingDirectory = state;
      EnvironmentFile = "/var/lib/roblox-design-dashboard/worker.env";
      TimeoutStartSec = 90;
      ExecStartPre = "${dashboard.python}/bin/python3 -B ${readiness}";
      ExecStart = "${dashboard.python}/bin/python3 -B ${dashboard}/share/roblox-design-dashboard/website/map_worker.py --server http://127.0.0.1:8765/roblox --repo ${source} --state ${state} --queue-db /var/lib/codex-queue/queue.sqlite3 --queue-repository ${repository} --bundle-root ${state}/bundles --owner mobile-dev-maps --poll 3";
      Restart = "on-failure";
      RestartSec = 5;
      UMask = "0027";
      NoNewPrivileges = true;
      PrivateTmp = true;
      PrivateDevices = true;
      ProtectHome = "read-only";
      ProtectSystem = "strict";
      BindReadOnlyPaths = [ "${repository}:${source}" ];
      ReadWritePaths = [ state "/var/lib/codex-queue" ];
      ProtectKernelTunables = true;
      ProtectControlGroups = true;
      RestrictSUIDSGID = true;
      RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
      MemoryMax = "512M";
    };
  };
}
