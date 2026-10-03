{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "3e5cc6933c62320ca1ae4f3131e9ef27a89f3ad6";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
