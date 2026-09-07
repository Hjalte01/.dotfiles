{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "53f950e212367cfd6b138f223617b40816554891";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
