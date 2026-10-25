{
  config,
  lib,
  pkgs,
  ...
}: let
  desktop = config.dotfiles.theme.desktop.enable;
  catalog =
    pkgs.runCommand "dotfiles-theme-catalog" {
      nativeBuildInputs = [pkgs.python3 pkgs.resvg];
    } ''
      python3 ${../scripts/theme-assets.py} ${../themes/palettes.json} $out
    '';
  theme = pkgs.callPackage ../pkgs/system-theme.nix {
    inherit desktop;
    swayosd = config.dotfiles.theme.desktop.swayosdPackage;
  };
in {
  options.dotfiles.theme.desktop = {
    enable = lib.mkEnableOption "desktop theme adapters and wallpaper service";
    swayosdPackage = lib.mkOption {
      type = lib.types.package;
      default = pkgs.swayosd;
      description = "SwayOSD package used when refreshing desktop colors.";
    };
  };
  config = {
    home.packages = [theme];
    qt = lib.mkIf desktop {
      enable = true;
      platformTheme.name = "qtct";
      style.name = "Fusion";
    };
    xdg.configFile."dotfiles-theme/catalog".source = catalog;
    xdg.configFile."mako/config" = lib.mkIf desktop {
      text = "include=~/.config/dotfiles-theme/current/mako.conf\n";
    };
    home.file.".local/lib/dotfiles_theme.py".source = ../scripts/dotfiles_theme.py;
    home.activation.systemTheme = lib.hm.dag.entryAfter ["linkGeneration"] ''
      run ${theme}/bin/system-theme apply --no-reload
    '';
    systemd.user.services.desktop-wallpaper = lib.mkIf desktop {
      Unit = {
        Description = "Persistent desktop wallpaper";
        PartOf = ["graphical-session.target"];
        After = ["graphical-session.target"];
      };
      Service = {
        ExecStart = "${theme}/bin/system-theme wallpaper-daemon";
        Restart = "on-failure";
        RestartSec = 2;
      };
    };
  };
}
