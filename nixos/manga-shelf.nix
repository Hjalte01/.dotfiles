{ pkgs, ... }:
let
  hub = pkgs.callPackage ../pkgs/vps-hub.nix {};
  python = "${pkgs.python3.withPackages (ps: [ps.pillow])}/bin/python3";
  tracker = "${hub}/share/manga-shelf/server.py";
  sharedConfig = {
    User = "manga-shelf";
    Group = "manga-shelf";
    StateDirectory = "manga-shelf";
    StateDirectoryMode = "0700";
    UMask = "0077";
    NoNewPrivileges = true;
    ProtectSystem = "strict";
    ProtectHome = true;
    PrivateDevices = true;
    PrivateTmp = true;
  };
in {
  users.groups.manga-shelf = {};
  users.users.manga-shelf = {
    isSystemUser = true;
    group = "manga-shelf";
  };

  systemd.services.manga-shelf = {
    description = "Private manga library and chapter refresh worker";
    wantedBy = ["multi-user.target"];
    wants = ["network-online.target"];
    after = ["network-online.target"];
    environment.PYTHONDONTWRITEBYTECODE = "1";
    serviceConfig = sharedConfig // {
      ExecStart = "${python} ${tracker} --state /var/lib/manga-shelf --port 8785";
      Restart = "on-failure";
      RestartSec = 2;
    };
  };

  systemd.services.manga-shelf-backup = {
    description = "Save a portable Manga Shelf backup";
    environment.PYTHONDONTWRITEBYTECODE = "1";
    serviceConfig = sharedConfig // {
      Type = "oneshot";
      ExecStart = "${python} ${tracker} --state /var/lib/manga-shelf --backup";
    };
  };

  systemd.timers.manga-shelf-backup = {
    wantedBy = ["timers.target"];
    timerConfig = {
      OnCalendar = "daily";
      Persistent = true;
    };
  };

  services.nginx.virtualHosts."vps-hub".locations = {
    "= /manga" = {
      return = "308 /manga/";
      extraConfig = "absolute_redirect off;";
    };
    "/manga/" = {
      proxyPass = "http://127.0.0.1:8785/";
      extraConfig = ''
        proxy_set_header Host $host;
        proxy_set_header Accept-Encoding "";
        client_max_body_size 16m;
      '';
    };
  };
}
