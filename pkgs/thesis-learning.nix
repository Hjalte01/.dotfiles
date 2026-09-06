{buildNpmPackage, nodejs_22}:
buildNpmPackage {
  pname = "thesis-learning";
  version = "0.1.0";
  nodejs = nodejs_22;

  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/thesis";
    rev = "78a87b250986600e346525463946bda57fceee74";
  };
  sourceRoot = "source/learning_site";

  npmDepsFetcherVersion = 2;
  npmDepsHash = "sha256-0ADCCV1tdQ8Dktb+NLFqDlbnKN6q4pZgOFTJuLTOIi8=";
  SITE_BASE = "/thesis/";
  ASTRO_TELEMETRY_DISABLED = "1";

  doCheck = true;
  checkPhase = ''
    runHook preCheck
    npm test
    runHook postCheck
  '';

  installPhase = ''
    runHook preInstall
    mkdir -p $out/share/thesis-learning
    cp -R dist/. $out/share/thesis-learning/
    runHook postInstall
  '';
}
