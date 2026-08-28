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
    rev = "b19f5b0c89bc1426bdd684435b5b8b1ac4b9203a";
    hash = "sha256-n/w3xY9YGRzYK1YXnLJEgIlBIM3tEtR1pqltCRG1FN4=";
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
