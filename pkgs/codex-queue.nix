{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "85739645c2440b5174e3c8a0c5cbfd88b33526cc";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
