{pkgs, ...}: let
  source = pkgs.runCommand "hendrix-vpn-python-source" {} ''
    mkdir -p $out/hendrix
    cp ${../scripts/hendrix}/{__init__,core,vpn}.py $out/hendrix/
  '';
  vpn = pkgs.writeShellApplication {
    name = "hendrix-vpn";
    runtimeInputs = [pkgs.openconnect pkgs.libsecret pkgs.systemd pkgs.glibc.bin pkgs.coreutils pkgs.zbar];
    text = ''
      export PYTHONPATH=${source}
      exec ${pkgs.python313}/bin/python3 -m hendrix.vpn "$@"
    '';
  };
  askpass = pkgs.writeShellApplication {
    name = "hendrix-ssh-askpass";
    text = ''
      exec ${vpn}/bin/hendrix-vpn --ssh-askpass "$@"
    '';
  };
in
  pkgs.symlinkJoin {
    name = "hendrix-desktop-login";
    paths = [vpn askpass];
  }
