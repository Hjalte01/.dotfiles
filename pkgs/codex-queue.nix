{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "4d17dbcb09c3f84b2145a714162e78f143b7860c";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
