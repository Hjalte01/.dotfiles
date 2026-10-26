{pkgs}: let
  python = pkgs.python313.withPackages (p: [p.pygobject3]);
in
  pkgs.writeShellApplication {
    name = "app-launcher";
    runtimeInputs = [pkgs.rofi pkgs.ghostty];
    text = ''
      export GI_TYPELIB_PATH="${pkgs.glib.out}/lib/girepository-1.0''${GI_TYPELIB_PATH:+:$GI_TYPELIB_PATH}"
      exec ${python}/bin/python3 ${../scripts/app-launcher.py} "$@"
    '';
  }
