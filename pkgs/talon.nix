{
  alsa-lib,
  dbus,
  fontconfig,
  lib,
  libGL,
  libpulseaudio,
  libx11,
  libxcb,
  libxcursor,
  libxext,
  libxfixes,
  libxi,
  libxinerama,
  libxkbcommon,
  libxrandr,
  libxtst,
  makeWrapper,
  sqlite,
  stdenv,
  systemd,
  zlib,
}:

stdenv.mkDerivation {
  pname = "talon";
  version = "2023-07-24";

  src = ../talon-linux.tar.xz;

  nativeBuildInputs = [
    makeWrapper
  ];

  installPhase = ''
    runHook preInstall

    mkdir -p "$out/opt/talon"
    cp -R . "$out/opt/talon"
    chmod +x "$out/opt/talon/talon"

    mkdir -p "$out/bin"
    makeWrapper "$out/opt/talon/talon" "$out/bin/talon" \
      --unset QT_AUTO_SCREEN_SCALE_FACTOR \
      --unset QT_SCALE_FACTOR \
      --set LC_NUMERIC C \
      --set QT_PLUGIN_PATH "$out/opt/talon/lib/plugins" \
      --prefix LD_LIBRARY_PATH : "${
        lib.makeLibraryPath [
          dbus
          fontconfig
          libGL
          libpulseaudio
          libx11
          libxcb
          libxcursor
          libxext
          libxfixes
          libxi
          libxinerama
          libxkbcommon
          libxrandr
          libxtst
          sqlite
          stdenv.cc.cc.lib
          systemd
          zlib
        ]
      }" \
      --prefix LD_LIBRARY_PATH : "${
        lib.makeLibraryPath [
          alsa-lib
        ]
      }" \
      --prefix LD_LIBRARY_PATH : "$out/opt/talon/lib:$out/opt/talon/resources/python/lib:$out/opt/talon/resources/pypy/lib:$out/opt/talon/resources/python/lib/python3.11/site-packages/numpy.libs"

    runHook postInstall
  '';

  meta = {
    description = "Talon Voice prebuilt Linux distribution";
    homepage = "https://talonvoice.com/";
    license = lib.licenses.unfree;
    platforms = [ "x86_64-linux" ];
  };
}
