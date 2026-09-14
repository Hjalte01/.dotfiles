{buildNpmPackage}:
buildNpmPackage {
  pname = "game-factory-gallery";
  version = "0.1.0";

  # Keep deployment source tied to a reviewed commit, never a dirty worktree.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/game_factory";
    rev = "b27bd2cc23e1247c087f6166f11af3519b15b315";
  };

  npmDepsFetcherVersion = 2;
  npmDepsHash = "sha256-+uTPGQ2RhrL+lGuB7OOi5QqTKCtuykSRxZgxUqO9Ixk=";
  npmBuildScript = "build:gallery";

  installPhase = ''
    runHook preInstall
    mkdir -p $out/share/game-factory-gallery
    cp -R dist/gallery/. $out/share/game-factory-gallery/
    runHook postInstall
  '';
}
