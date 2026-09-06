{buildNpmPackage}:
buildNpmPackage {
  pname = "cookbook";
  version = "1.0.0";
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/hjaltes-cookbook";
    rev = "05547e128574c878fb0f157a3322f1b88e3cb413";
  };
  npmDepsFetcherVersion = 2;
  npmDepsHash = "sha256-liUJ/0E2FXW0VwijuzrRJANZA2obqzzAcFLEEkSv2TY=";
  VITE_BASE_PATH = "/cookbook/";
  installPhase = ''
    runHook preInstall
    mkdir -p $out/share/cookbook
    cp -R dist/. $out/share/cookbook/
    runHook postInstall
  '';
}
