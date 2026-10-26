{pkgs, ...}: {
  # Hibernate can leave Codex's per-thread WebSockets silently blackholed.
  # system-sleep post hooks run before user.slice thaws, so these connections
  # all predate sleep. Reset only Codex's public HTTPS sockets and let it retry.
  environment.etc."systemd/system-sleep/codex-reconnect".source =
    pkgs.writeShellScript "codex-reconnect" ''
      if [ "$1" = post ]; then
        exec ${pkgs.coreutils}/bin/timeout --kill-after=1s 15s \
          ${pkgs.python3}/bin/python3 ${../scripts/codex-reconnect.py} \
          --ss ${pkgs.iproute2}/bin/ss --apply
      fi
    '';
}
