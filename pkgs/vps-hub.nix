{stdenvNoCC}:
stdenvNoCC.mkDerivation {
  pname = "vps-hub";
  version = "0.1.0";

  # Keep deployment source tied to a reviewed commit, never a dirty worktree.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/vps-hub";
    rev = "6eff0eced4ee748c3961d986a96c1994cd2bb553";
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
