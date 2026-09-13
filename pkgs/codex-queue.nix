{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "6e3cb6291b381a4e41d0f09cde2e1e2aa8ec6dac";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
