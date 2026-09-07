{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "3c6868204a9d55d8221bbac0f8268933d2fcb84f";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
