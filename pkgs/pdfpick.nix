{pkgs, ...}:
pkgs.writeShellApplication {
  name = "pdfpick";
  runtimeInputs = [pkgs.fd pkgs.fzf pkgs.poppler-utils pkgs.xdg-user-dirs];
  text = ''
    exec ${pkgs.python3}/bin/python3 ${../scripts/pdfpick.py} "$@"
  '';
}
