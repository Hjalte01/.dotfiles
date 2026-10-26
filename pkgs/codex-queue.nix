{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "b82e4793bbfaa5b365bb0768af24627a838b4b4e";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
