{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "c6e91fb24f6b58b7a254ce8d6c0b718be6eaec14";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
