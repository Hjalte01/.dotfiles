{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "5d03546b6fc9cb4b25c83d36e4f49f9c686db209";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
