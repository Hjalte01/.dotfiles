{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "9886d0e20be3e62fe41bf6424a4f24db09abe1b4";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
