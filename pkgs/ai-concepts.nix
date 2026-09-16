{stdenvNoCC, nodejs}:
stdenvNoCC.mkDerivation {
  pname = "ai-concepts";
  version = "1.0.0";
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/ai_concepts";
    rev = "29c457db8f18ebe19a6880c73b435966e4411f66";
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
