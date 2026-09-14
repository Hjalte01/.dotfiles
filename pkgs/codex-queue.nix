{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "3ddf22a39bb1fe86428a3ad1d547461dad6cb92c";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
