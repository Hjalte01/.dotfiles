{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "90cc899103d951a92d58cf549d602f013171fb46";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
