{pkgs, ...}: let
  python = pkgs.python313.withPackages (p: [p.textual]);
  source = pkgs.runCommand "hendrix-python-source" {} ''
    mkdir -p $out/hendrix
    cp ${../scripts/hendrix}/*.py $out/hendrix/
  '';
  cli = pkgs.writeShellApplication {
    name = "hendrix";
    runtimeInputs = [pkgs.openssh pkgs.rsync pkgs.coreutils pkgs.wl-clipboard pkgs.xclip];
    text = ''
      export PYTHONPATH=${source}
      exec ${python}/bin/python3 -m hendrix.cli "$@"
    '';
  };
  tui = pkgs.writeShellApplication {
    name = "hendrix-tui";
    text = ''
      exec ${cli}/bin/hendrix tui "$@"
    '';
  };
in
  pkgs.symlinkJoin {
    name = "hendrix-tools";
    paths = [cli tui];
  }
