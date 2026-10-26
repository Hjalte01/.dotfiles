{ stdenvNoCC, python3, nodejs_22, git, makeWrapper }:
stdenvNoCC.mkDerivation {
  pname = "roblox-design-dashboard";
  version = "1.0.0";
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/roblox-visual-dashboard";
    rev = "bf8c9510143fcc9da8dcf3069ecee402a6f74628";
  };
  dontBuild = true;
  nativeBuildInputs = [ makeWrapper ];
  nativeCheckInputs = [ python3 nodejs_22 git ];
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    python3 -B -m unittest discover -s website/tests -v
    node --check website/static/app.js
    runHook postCheck
  '';
  installPhase = ''
    runHook preInstall
    mkdir -p "$out/share/roblox-design-dashboard" "$out/bin"
    cp -R website "$out/share/roblox-design-dashboard/"
    makeWrapper ${python3}/bin/python3 "$out/bin/roblox-design-dashboard" \
      --add-flags "-B $out/share/roblox-design-dashboard/website/app.py"
    runHook postInstall
  '';
}
