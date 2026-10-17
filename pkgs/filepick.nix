{
  lib,
  rustPlatform,
}:
rustPlatform.buildRustPackage {
  pname = "filepick";
  version = "0.1.0";
  src = lib.fileset.toSource {
    root = ./filepick;
    fileset = lib.fileset.unions [
      ./filepick/Cargo.toml
      ./filepick/Cargo.lock
      ./filepick/src
    ];
  };
  DOTFILES_THEME_RS = ./desktop-theme.rs;
  cargoHash = "sha256-tyy0iiw3ZS3QTx6KRw5APrieOv5JLdRdLffirpVIDZk=";

  meta = {
    description = "Vim-style fuzzy file picker with Wayland file copying and drag handoff";
    mainProgram = "filepick";
    platforms = lib.platforms.linux;
    license = lib.licenses.mit;
  };
}
