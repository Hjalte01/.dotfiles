{buildNpmPackage, nodejs_22}:
buildNpmPackage {
  pname = "thesis-learning";
  version = "0.1.0";
  nodejs = nodejs_22;

  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/thesis";
    rev = "bb8b46a24fd9a6671e1f5635d8aa9dc97ea07d2c";
  };
  sourceRoot = "source/learning_site";

  npmDepsFetcherVersion = 2;
  npmDepsHash = "sha256-pHwxJyzA3poxLbdWBFYSfYKZaifhnI6AWKrSIyg9Rmo=";
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
