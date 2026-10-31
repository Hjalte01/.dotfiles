{ stdenvNoCC, python3, nodejs_22, git, makeWrapper, callPackage }:
let
  python = python3.withPackages (p: [ p.numpy p.pillow p.flask p.pywebpush p.cryptography ]);
  queue = callPackage ./codex-queue.nix {};
in
stdenvNoCC.mkDerivation {
  pname = "roblox-design-dashboard";
  version = "1.0.0";
  src = import ./roblox-studio-source.nix;
  dontBuild = true;
  nativeBuildInputs = [ makeWrapper ];
  nativeCheckInputs = [ python nodejs_22 git ];
  PYTHONPATH = "${queue}/${python3.sitePackages}";
  passthru = { inherit python; };
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    python3 -B -m unittest discover -s website/tests -v
    node --check website/static/app.js
    node --check website/studio_static/studio.js
    node --check website/studio_static/nav.js
    runHook postCheck
  '';
  installPhase = ''
    runHook preInstall
    mkdir -p "$out/share/roblox-design-dashboard" "$out/bin"
    cp -R website "$out/share/roblox-design-dashboard/"
    makeWrapper ${python}/bin/python3 "$out/bin/roblox-design-dashboard" \
      --add-flags "-B $out/share/roblox-design-dashboard/website/app.py"
    runHook postInstall
  '';
}
