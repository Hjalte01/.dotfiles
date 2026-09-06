{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "3c85cac6255dbf898828a058bd55ae796fba2b75";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
