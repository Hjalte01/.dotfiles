{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "58ae4883a5bf3a0ef1df12699882ee4a76b8d6c4";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
