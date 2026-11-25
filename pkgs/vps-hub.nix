{stdenvNoCC}:
stdenvNoCC.mkDerivation {
  pname = "vps-hub";
  version = "0.1.0";

  # Keep deployment source tied to a reviewed commit, never a dirty worktree.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/vps-hub";
    rev = "f5b59f6216f415b65369280a06447699a4c8d064";
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
