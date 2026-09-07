{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "7905c7df1e4b8b9693d5c965f8dd0a4d8a51e6ff";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
