{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "c2ba5a15cac3a589460e64006ef5b2ab465d73da";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
