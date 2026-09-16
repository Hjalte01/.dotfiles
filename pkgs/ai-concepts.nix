{stdenvNoCC, nodejs}:
stdenvNoCC.mkDerivation {
  pname = "ai-concepts";
  version = "1.0.0";
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/ai_concepts";
    rev = "5d15361cff72e236e62c15769a1ce813500e8ec7";
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
