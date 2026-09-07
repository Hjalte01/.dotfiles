{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "bca7f14b38468babb5a7b72efceca26768e7d12b";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
