{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "65fb1066dbcb1e40b0e48cac574df97119989b16";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
