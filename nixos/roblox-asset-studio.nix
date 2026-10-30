# VPS-only reference review and finite, serial asset production.
{ pkgs, ... }:
let
  asset = pkgs.callPackage ../pkgs/roblox-asset-studio.nix {};
  queue = pkgs.callPackage ../pkgs/codex-queue.nix {};
  state = "/var/lib/roblox-asset-studio";
  source = "/srv/roblox-asset-source";
  repository = "/home/hjalte/documents/roblox-gamemodes";
  helper = "${asset}/share/roblox-asset-studio/website/asset_tools/reference_set.py";
  readiness = pkgs.writeText "roblox-asset-worker-ready.py" ''
    import json,time,urllib.request,urllib.error
    targets = [
        ("http://127.0.0.1:8787/healthz", "${queue.src.rev}"),
        ("http://127.0.0.1:8766/roblox-assets/api/health", "${asset.src.rev}"),
    ]
    for attempt in range(45):
        ready = True
        for url, revision in targets:
            try:
                with urllib.request.urlopen(url, timeout=1) as response:
                    health = json.loads(response.read(8192))
                ready = ready and (health.get("ok") is True or health.get("status") == "ok") and health.get("revision") == revision
            except (OSError, ValueError, urllib.error.URLError):
                ready = False
        if ready:
            break
        time.sleep(.5)
    else:
        raise SystemExit("Asset Studio and Codex Queue are not ready at their pinned revisions; refusing to submit asset jobs.")
  '';
in {
  systemd.tmpfiles.rules = [
    "d ${source} 0755 root root -"
    "d ${state} 0700 hjalte users -"
    "d ${state}/jobs 0700 hjalte users -"
    "d ${state}/seed 0700 hjalte users -"
  ];
  systemd.services.roblox-asset-studio = {
    description = "Private Roblox asset reference reviews";
    wantedBy = [ "multi-user.target" ];
    after = [ "network.target" ];
    environment = {
      PYTHONDONTWRITEBYTECODE = "1";
      PYTHONUNBUFFERED = "1";
      ASSET_STUDIO_ALLOWED_HOSTS = "mobile-dev.tail55f864.ts.net,mobile-dev";
      ASSET_STUDIO_REVISION = asset.src.rev;
    };
    serviceConfig = {
      User = "hjalte";
      Group = "users";
      StateDirectory = "roblox-asset-studio";
      StateDirectoryMode = "0700";
      WorkingDirectory = state;
      ExecStartPre = "${asset}/bin/roblox-asset-studio --repo ${source} --state ${state} --seed-root ${state}/seed --seed-only";
      ExecStart = "${asset}/bin/roblox-asset-studio --repo ${source} --state ${state} --host 127.0.0.1 --port 8766 --base-path /roblox-assets";
      Restart = "on-failure";
      RestartSec = 3;
      UMask = "0077";
      NoNewPrivileges = true;
      PrivateTmp = true;
      PrivateDevices = true;
      ProtectHome = true;
      ProtectSystem = "strict";
      BindReadOnlyPaths = [ "${repository}:${source}" ];
      ProtectKernelTunables = true;
      ProtectControlGroups = true;
      RestrictSUIDSGID = true;
      RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
      MemoryMax = "384M";
    };
  };
  systemd.services.roblox-asset-worker = {
    description = "Serial Sol Low asset production through Codex Queue";
    wantedBy = [ "multi-user.target" ];
    after = [ "roblox-asset-studio.service" "codex-queue.service" ];
    wants = [ "roblox-asset-studio.service" "codex-queue.service" ];
    path = [ asset.python pkgs.nodejs_22 pkgs.git pkgs.coreutils pkgs.ripgrep ];
    environment = {
      PYTHONDONTWRITEBYTECODE = "1";
      PYTHONUNBUFFERED = "1";
      PYTHONPATH = "${queue}/${pkgs.python3.sitePackages}";
      CODEX_HOME = "/home/hjalte/.codex";
      CODEX_QUEUE_ASSET_ROOT = "${state}/jobs";
      ASSET_STUDIO_REFERENCE_HELPER = helper;
      ASSET_STUDIO_TOOLKIT = "${asset.toolkit}";
      ASSET_STUDIO_QUEUE_REVISION = queue.src.rev;
    };
    serviceConfig = {
      User = "hjalte";
      Group = "users";
      StateDirectory = "roblox-asset-studio";
      StateDirectoryMode = "0700";
      WorkingDirectory = state;
      TimeoutStartSec = 150;
      ExecStartPre = "${asset.python}/bin/python3 -B ${readiness}";
      ExecStart = "${asset}/bin/roblox-asset-worker --repo ${source} --state ${state} --queue-db /var/lib/codex-queue/queue.sqlite3 --queue-repository ${repository} --owner mobile-dev-assets --poll 3";
      Restart = "on-failure";
      RestartSec = 5;
      UMask = "0077";
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
  # Same global serial worker and allowance gate as every other Codex job.
  systemd.services.codex-queue.environment.CODEX_QUEUE_ASSET_ROOT = "${state}/jobs";
  systemd.services.codex-queue.serviceConfig.ReadWritePaths = [ "${state}/jobs" ];
}
