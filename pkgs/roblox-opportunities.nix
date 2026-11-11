{ stdenvNoCC, python3, makeWrapper, nodejs }:
stdenvNoCC.mkDerivation {
  pname = "roblox-opportunities";
  version = "2026-11-11";

  # Retain the supplied release outside Git and verify its exact NAR hash.
  # The original archive SHA256 is recorded in docs/roblox-opportunities.md.
  src = builtins.fetchTarball {
    url = "file:///srv/roblox-opportunities/releases/55809bd5303f9991290fcfd3710c71917d6dbb818d1da9882b5424e0d5a54683.tar.gz";
    sha256 = "1rcrm9ay1s9m88a7wd95lip673i1dvciv5sz2d7m0q0pan8w9ypm";
  };
  patches = [ ./roblox-opportunities/roblox-chart-api.patch ];
  nativeBuildInputs = [ makeWrapper ];
  nativeCheckInputs = [ nodejs ];
  dontBuild = true;
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    PYTHONPATH=. ${python3}/bin/python3 -B -W error::ResourceWarning ${./roblox-opportunities/test_server.py}
    cp ${./roblox-opportunities/test_app.cjs} test_app.cjs
    node --check app.js
    node --test test_app.cjs
    runHook postCheck
  '';
  installPhase = ''
    runHook preInstall
    mkdir -p $out/share/roblox-opportunities $out/bin
    cp server.py index.html app.js style.css ideas.json market-seed.json $out/share/roblox-opportunities/
    cp -R art $out/share/roblox-opportunities/
    makeWrapper ${python3}/bin/python3 $out/bin/roblox-opportunities \
      --add-flags "$out/share/roblox-opportunities/server.py"
    runHook postInstall
  '';
}
