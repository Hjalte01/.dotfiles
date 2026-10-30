{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "f182d6a657a265d05df2cc5cb4338d0968be1750";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
