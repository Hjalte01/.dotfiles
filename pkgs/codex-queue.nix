{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "273d16679c70b219998f76a5d2abf0db1a9728ad";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
