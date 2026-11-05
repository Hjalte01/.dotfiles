{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "ba76f4531edb7291b64d9f32606c4726a2eb1be8";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
