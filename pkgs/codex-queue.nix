{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "6321093916968378ac91d9c308e1d9657a54667d";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
