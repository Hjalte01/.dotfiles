{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "bc1545ba974b8544bbe0776700cd098495e78db1";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
