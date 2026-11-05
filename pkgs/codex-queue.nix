{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "3e2c6f35dfa141775b23b20820d93193b795e4cd";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
