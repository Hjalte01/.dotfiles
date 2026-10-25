{
  lib,
  rustPlatform,
  makeBinaryWrapper,
  wl-clipboard,
  wtype,
  libnotify,
  systemd,
}:
rustPlatform.buildRustPackage {
  pname = "dictation";
  version = "0.1.0";
  src = lib.fileset.toSource {
    root = ./dictation;
    fileset = lib.fileset.unions [
      ./dictation/Cargo.toml
      ./dictation/Cargo.lock
      ./dictation/terms.tsv
      ./dictation/src
      ./dictation/tests
    ];
  };
  cargoLock.lockFile = ./dictation/Cargo.lock;
  nativeBuildInputs = [makeBinaryWrapper];
  postInstall = ''
    wrapProgram $out/bin/dictation \
      --prefix PATH : ${lib.makeBinPath [wl-clipboard wtype libnotify systemd]}
    # Handy's external-script hook passes just the transcript as one argument.
    makeWrapper $out/bin/dictation $out/bin/dictation-paste --add-flags paste
    makeWrapper $out/bin/dictation $out/bin/handy-toggle --add-flags toggle
  '';
  meta = {
    description = "Local Rust dictation controls and scientific notation correction";
    mainProgram = "dictation";
    platforms = lib.platforms.linux;
    license = lib.licenses.mit;
  };
}
