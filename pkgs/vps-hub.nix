{stdenvNoCC}:
stdenvNoCC.mkDerivation {
  pname = "vps-hub";
  version = "0.1.0";

  # Keep deployment source tied to a reviewed commit, never a dirty worktree.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/vps-hub";
    rev = "7a81c2e88f66695e8d8417f3aa84ef0094406aa2";
  };

  installPhase = ''
    runHook preInstall
    mkdir -p $out/share/vps-hub
    cp -R public/. $out/share/vps-hub/
    runHook postInstall
  '';
}
