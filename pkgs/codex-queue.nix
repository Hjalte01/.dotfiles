{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "ad940b6dc62f25059e509316358a2e1bd336f9a6";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
