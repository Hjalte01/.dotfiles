{pkgs, ...}: let
  python = pkgs.python313.withPackages (p: [p.textual p.textual-image p.pillow]);
  source = pkgs.runCommand "imagepick-python-source" {} ''
    mkdir -p $out
    cp ${../scripts/imagepick.py} $out/imagepick.py
    cp ${../scripts/imagepick_core.py} $out/imagepick_core.py
    cp ${../scripts/dotfiles_theme.py} $out/dotfiles_theme.py
  '';
  picker = pkgs.writeShellApplication {
    name = "imagepick";
    runtimeInputs = [pkgs.cliphist pkgs.satty pkgs.wl-clipboard];
    text = ''
      exec ${python}/bin/python3 ${source}/imagepick.py "$@"
    '';
  };
  menu = pkgs.writeShellApplication {
    name = "imagepick-menu";
    runtimeInputs = [pkgs.ghostty];
    text = ''
      exec ghostty --class=local.imagepick --title="Recent images" -e ${picker}/bin/imagepick "$@"
    '';
  };
in
  pkgs.symlinkJoin {
    name = "imagepick";
    paths = [picker menu];
    meta = {
      description = "Browse, crop, and annotate recent screenshots and clipboard images";
      mainProgram = "imagepick";
      platforms = pkgs.lib.platforms.linux;
    };
  }
