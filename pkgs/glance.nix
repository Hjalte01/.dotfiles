{
  lib,
  stdenvNoCC,
  python3,
  gtk3,
  gtk-layer-shell,
  gobject-introspection,
  wrapGAppsHook3,
}: let
  python = python3.withPackages (ps: [ps.pygobject3]);
in
  stdenvNoCC.mkDerivation {
    pname = "glance";
    version = "0.1.0";
    dontUnpack = true;
    nativeBuildInputs = [gobject-introspection wrapGAppsHook3];
    buildInputs = [gtk3 gtk-layer-shell];
    installPhase = ''
      runHook preInstall
      install -Dm755 ${../scripts/glance.py} $out/bin/glance
      substituteInPlace $out/bin/glance \
        --replace-fail '#!/usr/bin/env python3' '#!${python}/bin/python3'
      runHook postInstall
    '';
    meta = {
      description = "Hold to peek at the time, date and battery; Escape pins";
      mainProgram = "glance";
      platforms = lib.platforms.linux;
    };
  }
