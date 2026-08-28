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
    rev = "aef008d4c1a9918d50e327dae7a6d414f5620824";
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
