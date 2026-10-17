{pkgs, ...}: let
  python = pkgs.python313.withPackages (p: [p.textual]);
  zoxideArchive = pkgs.fetchurl {
    url = "https://github.com/ajeetdsouza/zoxide/releases/download/v0.10.0/zoxide-0.10.0-x86_64-unknown-linux-musl.tar.gz";
    hash = "sha256-LZM4W5nz6CzycBYJob/8rYY/vrdao/5+tr5NKb5osa4=";
  };
  remoteZoxide =
    pkgs.runCommand "hendrix-remote-zoxide-0.10.0" {
      nativeBuildInputs = [pkgs.gnutar pkgs.gzip];
    } ''
      mkdir -p $out/bin
      tar -xzf ${zoxideArchive} -C $out/bin zoxide
      chmod 755 $out/bin/zoxide
    '';
  source = pkgs.runCommand "hendrix-python-source" {} ''
    mkdir -p $out/hendrix
    cp ${../scripts/hendrix}/*.py $out/hendrix/
    cp ${../scripts/dotfiles_theme.py} $out/dotfiles_theme.py
    cp ${../scripts/hendrix}/*.bash $out/hendrix/
  '';
  cli = pkgs.writeShellApplication {
    name = "hendrix";
    runtimeInputs = [pkgs.openssh pkgs.rsync pkgs.coreutils pkgs.ncurses pkgs.wl-clipboard pkgs.xclip pkgs.netcat-openbsd pkgs.glibc.bin];
    text = ''
      export PYTHONPATH=${source}
      export HENDRIX_REMOTE_ZOXIDE=${remoteZoxide}/bin/zoxide
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
