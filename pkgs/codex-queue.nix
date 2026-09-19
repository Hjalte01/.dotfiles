{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "0172e73070d37049ce784303190917c14d0d7dba";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
