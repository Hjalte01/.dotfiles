{stdenvNoCC, nodejs}:
stdenvNoCC.mkDerivation {
  pname = "ai-concepts";
  version = "1.0.0";
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/ai_concepts";
    rev = "b09617fbc288b833cb156f35cdde3a6cc5846baf";
  };
  nativeCheckInputs = [nodejs];
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    node scripts/check.mjs
    node --test test/math.test.js
    runHook postCheck
  '';
  installPhase = ''
    runHook preInstall
    mkdir -p $out/share/ai-concepts
    cp -R public/. $out/share/ai-concepts/
    runHook postInstall
  '';
}
