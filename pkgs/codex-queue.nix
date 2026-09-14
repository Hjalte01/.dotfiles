{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "b080bedd43e10e3f9e45a77bb6390d10a2c1feb3";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
