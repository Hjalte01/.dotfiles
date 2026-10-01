{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "b398a152289847ccf730f547a83ed62ee742c86b";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
