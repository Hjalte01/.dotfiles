{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "e0e0fa92faa000cbdc6b573647dd8af839c330b1";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
