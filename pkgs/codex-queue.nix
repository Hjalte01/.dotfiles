{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "d5968d10a07f37421d39548feb26a7bf4585ac35";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
