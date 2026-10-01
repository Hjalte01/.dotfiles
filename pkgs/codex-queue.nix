{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "d7eaf2e52322d726302fc18848f85ec8344ea4f5";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
