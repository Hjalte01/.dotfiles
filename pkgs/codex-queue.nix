{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "0c5169b00b9250b5129487c34342b67dd801cb12";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
