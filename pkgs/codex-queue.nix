{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "58232692947a4f4c5f563968f0ac889b7b38dfb4";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
