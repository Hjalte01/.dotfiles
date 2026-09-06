{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "932971ac099d9f5a40a6bcceb99af35702e2a78e";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
