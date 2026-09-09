{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "65e076811b9fcdf8547d2a12e7bf2502bac5c567";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
