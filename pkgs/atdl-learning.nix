{buildNpmPackage, nodejs_22}:
buildNpmPackage {
  pname = "atdl-learning";
  version = "0.1.0";
  nodejs = nodejs_22;

  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/atdl_learning_site";
    rev = "9b4d42706caf9b84933a3f115118b9de6ccc91e7";
  };

  npmDepsFetcherVersion = 2;
  npmDepsHash = "sha256-adTEJH/q19AvxFudsMRawtRu/plcsTZ7hHL6MZy6b48=";
  ASTRO_TELEMETRY_DISABLED = "1";

  # Keep upstream GitHub Pages defaults while building for the private VPS.
  postPatch = ''
    substituteInPlace astro.config.mjs \
      --replace-fail 'const base = "/atdl_learning_site";' 'const base = "/atdl";' \
      --replace-fail 'https://hjalte01.github.io' 'https://mobile-dev.tail55f864.ts.net'
  '';

  installPhase = ''
    runHook preInstall
    mkdir -p $out/share/atdl-learning
    cp -R dist/. $out/share/atdl-learning/
    runHook postInstall
  '';
}
