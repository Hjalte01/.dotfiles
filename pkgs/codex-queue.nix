{
  lib,
  fetchgit,
  python3Packages,
}:
python3Packages.buildPythonApplication {
  pname = "codex-queue";
  version = "0.1.0";
  pyproject = true;

  # The application is a standalone local repository. Keep this pin explicit so
  # mobile-dev rebuilds use reviewed, committed source rather than a dirty tree.
  src = fetchgit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "f68cc8723cb78fd02e069fcbdea24ac42eb10729";
    hash = "sha256-u8Eu1XXHB6v9JaBBjcz6KH7dudW5UtHoT3rFTsJnyn4=";
  };

  build-system = [python3Packages.setuptools];
  dependencies = [python3Packages.flask];

  nativeCheckInputs = [python3Packages.pytestCheckHook];
  pythonImportsCheck = ["codex_queue"];

  meta = {
    description = "Tailnet dashboard for serialized unattended Codex runs";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
    mainProgram = "codex-queue";
  };
}
