{
  lib,
  rustPlatform,
  runCommand,
  pkg-config,
  makeBinaryWrapper,
  gtk3,
  gtk-layer-shell,
  pipewire,
  systemd,
  handy,
  dictation,
  model,
}: let
  # Use the exact, ABI-compatible inference library already built by Handy.
  # transcribe-cpp's supported TRANSCRIBE_DIR interface avoids recompiling the
  # native engines and Vulkan shaders for a second frontend.
  inference = runCommand "dictation-inference-0.2.4" {} ''
    mkdir -p $out/lib
    for library in ${handy}/lib/Handy/*.so*; do
      ln -s "$library" "$out/lib/$(basename "$library")"
    done
    ln -s ${handy}/lib/Handy/libtranscribe.so.0.2 $out/lib/libtranscribe.so
    cat > $out/lib/transcribe-link.json <<'JSON'
    {"shared":true,"lib_dir":"lib","libraries":["transcribe"],"module_dir":"lib"}
    JSON
  '';
in
  rustPlatform.buildRustPackage {
    pname = "dictation-live";
    version = "0.1.0";
    src = lib.fileset.toSource {
      root = ./.;
      fileset = lib.fileset.unions [
        ./dictation-live/Cargo.toml
        ./dictation-live/Cargo.lock
        ./dictation-live/src
        ./dictation/Cargo.toml
        ./dictation/Cargo.lock
        ./dictation/terms.tsv
        ./dictation/src
      ];
    };
    cargoRoot = "dictation-live";
    buildAndTestSubdir = "dictation-live";
    cargoLock.lockFile = ./dictation-live/Cargo.lock;
    nativeBuildInputs = [pkg-config makeBinaryWrapper];
    buildInputs = [gtk3 gtk-layer-shell inference];
    DOTFILES_THEME_RS = ./desktop-theme.rs;
    TRANSCRIBE_DIR = inference;
    postInstall = ''
        wrapProgram $out/bin/dictation-live \
          --set-default DICTATION_MODEL_PATH ${model} \
          --set-default DICTATION_BACKEND_DIR ${handy}/lib/Handy \
          --prefix PATH : ${lib.makeBinPath [pipewire dictation systemd]}
      makeWrapper $out/bin/dictation-live $out/bin/dictation-live-toggle --add-flags toggle
    '';
    meta = {
      description = "Native Rust live dictation overlay with local recognition and a microphone spectrum";
      mainProgram = "dictation-live";
      platforms = lib.platforms.linux;
      license = lib.licenses.mit;
    };
  }
