{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "6057ac16a8fb50c9a9199ce8bcffe31ae4c3565d";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
