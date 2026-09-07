{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "e8d9f7812249aee27bb29bf9fa77691350b1c74b";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
