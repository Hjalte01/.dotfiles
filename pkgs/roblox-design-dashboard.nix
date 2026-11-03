{ stdenvNoCC, python3, nodejs_22, git, makeWrapper, callPackage }:
let
  python = python3.withPackages (p: [ p.numpy p.pillow p.flask p.pywebpush p.cryptography ]);
  queue = callPackage ./codex-queue.nix {};
  toolkit = (callPackage ./roblox-asset-studio.nix {}).toolkit;
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
    node --test website/tests/test_studio_ui.mjs
    for script in website/studio_static/creative*.js; do node --check "$script"; done
    for tests in website/tests/test_creative*.mjs; do node --test "$tests"; done
    runHook postCheck
  '';
  installPhase = ''
    runHook preInstall
    mkdir -p "$out/share/roblox-design-dashboard" "$out/bin"
    cp -R website "$out/share/roblox-design-dashboard/"
    browser="$out/share/roblox-design-dashboard/website/studio_static/vendor/three"
    mkdir -p "$browser/addons/controls" "$browser/addons/loaders" "$browser/addons/utils"
    cp ${toolkit}/node_modules/three/build/three.module.js ${toolkit}/node_modules/three/build/three.core.js "$browser/"
    cp ${toolkit}/node_modules/three/examples/jsm/controls/OrbitControls.js ${toolkit}/node_modules/three/examples/jsm/controls/TransformControls.js "$browser/addons/controls/"
    cp ${toolkit}/node_modules/three/examples/jsm/loaders/GLTFLoader.js "$browser/addons/loaders/"
    cp ${toolkit}/node_modules/three/examples/jsm/utils/BufferGeometryUtils.js "$browser/addons/utils/"
    makeWrapper ${python}/bin/python3 "$out/bin/roblox-design-dashboard" \
      --add-flags "-B $out/share/roblox-design-dashboard/website/app.py"
    runHook postInstall
  '';
}
