{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "088dcca38857fa76fba9b2be1b077c3930bc5a3e";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
