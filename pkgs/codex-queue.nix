{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "c102740417a3eabcc86714b1d57e9a0a09a2ce5b";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
