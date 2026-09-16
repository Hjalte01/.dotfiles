{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "88eb03138e15498fb751f3a873ecfa0abb7a1470";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
