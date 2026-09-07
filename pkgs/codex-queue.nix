{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "17885961a72a0f8596d3f176dd56c3e6e4b63d64";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
