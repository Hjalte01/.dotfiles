{
  lib,
  python3Packages,
}:
python3Packages.buildPythonApplication {
  pname = "codex-queue";
  version = "0.1.0";
  pyproject = true;

  # The application is a standalone local repository. Keep this pin explicit so
  # mobile-dev rebuilds use reviewed, committed source rather than a dirty tree.
  src = builtins.fetchGit {
    url = "file:///home/hjalte/documents/codex-queue";
    rev = "bfceddd6a439a096c10896b92699ceeb3920ed42";
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
