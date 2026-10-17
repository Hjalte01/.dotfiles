{ lib, rustPlatform, libxkbcommon, dejavu_fonts }:
rustPlatform.buildRustPackage {
  pname = "window-overview";
  version = "0.2.0";
  src = lib.fileset.toSource {
    root = ./window-overview;
    fileset = lib.fileset.unions [
      ./window-overview/Cargo.toml
      ./window-overview/Cargo.lock
      ./window-overview/src
    ];
  };
  cargoHash = "sha256-E8WDdiyby9h0o8Sm/e0W6tjwbdgOISm7pwx78cAPtKY=";
  buildInputs = [ libxkbcommon ];
  DOTFILES_THEME_RS = ./desktop-theme.rs;
  OVERVIEW_FONT = "${dejavu_fonts}/share/fonts/truetype/DejaVuSans.ttf";
  meta = {
    description = "Spatial native Wayland window and workspace overview";
    mainProgram = "window-overview";
    platforms = lib.platforms.linux;
    license = lib.licenses.mit;
  };
}
