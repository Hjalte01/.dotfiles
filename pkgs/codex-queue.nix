{callPackage}: let
  # Pin committed application source; reuse its runtime dependencies and checks.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "5524188c843555fab2aaa4bf01ad662695cbfe46";
  };
in
  callPackage (src + "/package.nix") {inherit src;}
