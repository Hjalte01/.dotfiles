{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "1249313c0aedef7e4340e0beb6d8dadea2e05a6f";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
