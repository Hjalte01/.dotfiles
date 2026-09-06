{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "1e19e7006d58dfd5888c7ccaa16c551a07b64720";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
