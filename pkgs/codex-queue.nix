{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "c35805f214d02c5ed512d5ff880569112748bbf4";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
