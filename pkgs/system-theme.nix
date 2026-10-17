{
  lib,
  rustPlatform,
  pkg-config,
  makeWrapper,
  wrapGAppsHook3,
  gtk3,
  gtk-layer-shell,
  glib,
  tmux,
  systemd,
  mako,
  swaybg,
  swayosd,
  desktop ? true,
}:
rustPlatform.buildRustPackage {
  pname = "system-theme";
  version = "0.2.0";
  src = lib.fileset.toSource {
    root = ./system-theme;
    fileset = lib.fileset.unions [./system-theme/Cargo.toml ./system-theme/Cargo.lock ./system-theme/src];
  };
  cargoLock.lockFile = ./system-theme/Cargo.lock;
  buildNoDefaultFeatures = true;
  buildFeatures = lib.optional desktop "desktop";
  nativeBuildInputs = [makeWrapper] ++ lib.optionals desktop [pkg-config wrapGAppsHook3];
  buildInputs = lib.optionals desktop [gtk3 gtk-layer-shell];
  dontWrapGApps = true;
  postInstall = ''
    wrapProgram $out/bin/system-theme \
      --set-default DOTFILES_THEME_DESKTOP ${
      if desktop
      then "1"
      else "0"
    } \
      --prefix PATH : ${lib.makeBinPath ([tmux] ++ lib.optionals desktop [systemd glib mako swaybg swayosd])} \
      ''${gappsWrapperArgs[@]}
  '';
  meta = {
    description = "Native theme switching and a live-preview Wayland appearance picker";
    mainProgram = "system-theme";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
  };
}
