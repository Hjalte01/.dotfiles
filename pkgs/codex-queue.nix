{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "a4f81bc46224f61a2943576b7f420249654ea2e6";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
