{stdenvNoCC}:
stdenvNoCC.mkDerivation {
  pname = "vps-hub";
  version = "0.1.0";

  # Keep deployment source tied to a reviewed commit, never a dirty worktree.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/vps-hub";
    rev = "649267bc0919ed27fc5e9d323b78b0a245883bf2";
  };

  installPhase = ''
    runHook preInstall
    mkdir -p $out/share/vps-hub
    cp -R public/. $out/share/vps-hub/
    runHook postInstall
  '';
}
