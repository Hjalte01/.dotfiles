{stdenvNoCC}:
stdenvNoCC.mkDerivation {
  pname = "vps-hub";
  version = "0.1.0";

  # Keep deployment source tied to a reviewed commit, never a dirty worktree.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/vps-hub";
    rev = "c21534b3c904c5824a30cd0d629c4cca68bb6f2b";
  };

  installPhase = ''
    runHook preInstall
    mkdir -p $out/share/vps-hub
    cp -R public/. $out/share/vps-hub/
    mkdir -p $out/share/manga-shelf
    cp -R manga/server.py manga/sources.py manga/public $out/share/manga-shelf/
    runHook postInstall
  '';
}
