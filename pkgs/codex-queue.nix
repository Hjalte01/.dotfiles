{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "36acf103e9e4c890ec916c5521b3039a36510f55";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
