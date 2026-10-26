{pkgs, ...}: let
  python = pkgs.python313.withPackages (p: [p.textual]);
  source = pkgs.runCommand "devices-python-source" {} ''
    mkdir -p $out/devices
    cp ${../scripts/devices}/*.py $out/devices/
    cp ${../scripts/dotfiles_theme.py} $out/dotfiles_theme.py
  '';
in
  pkgs.writeShellApplication {
    name = "devices";
    runtimeInputs = [pkgs.openssh pkgs.fastfetch pkgs.util-linux];
    text = ''
      export PYTHONPATH=${source}
      export DEVICES_SEED=${../data/devices.json}
      exec ${python}/bin/python3 -m devices.cli "$@"
    '';
  }
