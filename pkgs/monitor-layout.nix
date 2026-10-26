{pkgs}:
pkgs.writeShellApplication {
  name = "monitor-layout";
  runtimeInputs = [pkgs.hyprland];
  text = ''
    exec ${pkgs.python3}/bin/python3 ${../scripts/monitor-layout.py} "$@"
  '';
}
