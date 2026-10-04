{pkgs, ...}: let
  source = pkgs.runCommand "hendrix-vpn-python-source" {} ''
    mkdir -p $out/hendrix
    cp ${../scripts/hendrix}/{__init__,core,vpn}.py $out/hendrix/
  '';
in
  pkgs.writeShellApplication {
    name = "hendrix-vpn";
    runtimeInputs = [pkgs.openconnect pkgs.openresolv pkgs.tailscale pkgs.libsecret pkgs.systemd pkgs.glibc.bin pkgs.coreutils];
    text = ''
      export PYTHONPATH=${source}
      exec ${pkgs.python313}/bin/python3 -m hendrix.vpn "$@"
    '';
  }
