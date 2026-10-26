{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "f18938a990735f0f0f4853a275fa5858ec9e2c1d";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
