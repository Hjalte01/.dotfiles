{stdenvNoCC}:
stdenvNoCC.mkDerivation {
  pname = "vps-hub";
  version = "0.1.0";

  # Keep deployment source tied to a reviewed commit, never a dirty worktree.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/vps-hub";
    rev = "8c10bbda6e2b508ac27c73faa4e9b31afdb90bb3";
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
