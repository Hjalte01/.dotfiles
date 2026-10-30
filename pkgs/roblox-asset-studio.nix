{ stdenvNoCC, python3, nodejs_22, makeWrapper, runCommand, importNpmLock, callPackage }:
let
  queue = callPackage ./codex-queue.nix {};
  source = builtins.fetchGit {
    url = "file:///home/hjalte/documents/roblox-gamemodes";
    rev = "8c332227b85e499e1316ff3548e33466a5001162";
  };
  toolkitSource = source + "/games/asset_design_lab/experiment/toolkit";
  modules = importNpmLock.buildNodeModules {
    npmRoot = toolkitSource;
    nodejs = nodejs_22;
    derivationArgs = { pname = "roblox-asset-toolkit-node-modules"; version = "1.0.0"; };
  };
  toolkit = runCommand "roblox-asset-toolkit" {} ''
    mkdir -p "$out"
    cp -R ${toolkitSource}/. "$out/"
    ln -s ${modules}/node_modules "$out/node_modules"
  '';
  python = python3.withPackages (p: [ p.numpy p.pillow p.flask p.pywebpush p.cryptography ]);
in stdenvNoCC.mkDerivation {
  pname = "roblox-asset-studio";
  version = "1.0.0";
  src = source;
  dontBuild = true;
  nativeBuildInputs = [ makeWrapper ];
  nativeCheckInputs = [ python nodejs_22 ];
  PYTHONPATH = "${queue}/${python3.sitePackages}";
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    test -f website/assets_app.py
    test -f website/asset_worker.py
    python3 -B -m unittest discover -s website/tests -p 'test_asset*.py' -q
    node --check website/asset_static/studio.js
    runHook postCheck
  '';
  passthru = { inherit toolkit python; };
  installPhase = ''
    runHook preInstall
    mkdir -p "$out/share/roblox-asset-studio" "$out/bin"
    cp -R website "$out/share/roblox-asset-studio/"
    makeWrapper ${python}/bin/python3 "$out/bin/roblox-asset-studio" \
      --add-flags "-B $out/share/roblox-asset-studio/website/assets_app.py"
    makeWrapper ${python}/bin/python3 "$out/bin/roblox-asset-worker" \
      --add-flags "-B $out/share/roblox-asset-studio/website/asset_worker.py" \
      --prefix PYTHONPATH : "${queue}/${python3.sitePackages}"
    runHook postInstall
  '';
}
