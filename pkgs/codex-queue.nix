{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "633c0cdfb8ba2fa7b5897e9f2a5565da9f91a8b4";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
