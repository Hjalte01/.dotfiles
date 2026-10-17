{ lib, rustPlatform, libxkbcommon, nerd-fonts, makeWrapper, hyprland, systemd }:
rustPlatform.buildRustPackage {
  pname = "desktop-which-key";
  version = "0.1.0";
  src = lib.fileset.toSource {
    root = ./desktop-which-key;
    fileset = lib.fileset.unions [
      ./desktop-which-key/Cargo.toml
      ./desktop-which-key/Cargo.lock
      ./desktop-which-key/src
    ];
  };
  cargoHash = "sha256-SbQ1t+b6GV2NLJTQhbhrAsJopXjVqMGOYruR7IndM5U=";
  buildInputs = [ libxkbcommon ];
  nativeBuildInputs = [ makeWrapper ];
  DOTFILES_THEME_RS = ./desktop-theme.rs;
  WHICH_KEY_FONT = "${nerd-fonts.jetbrains-mono}/share/fonts/truetype/NerdFonts/JetBrainsMono/JetBrainsMonoNerdFont-Regular.ttf";
  postInstall = ''
    wrapProgram $out/bin/desktop-which-key --prefix PATH : ${lib.makeBinPath [ hyprland systemd ]}
  '';
  meta = {
    description = "Searchable native Wayland which-key for Hyprland";
    mainProgram = "desktop-which-key";
    platforms = lib.platforms.linux;
    license = lib.licenses.mit;
  };
}
