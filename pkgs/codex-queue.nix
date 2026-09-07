{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "d142e97fc4b1a07e860202038442719b76d53e56";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
