{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "8e48e0c14e1a22872cdbbe8ddcf715026c0db019";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
