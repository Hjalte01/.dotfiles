{
  lib,
  fetchFromGitHub,
  python313Packages,
}:
python313Packages.buildPythonApplication {
  pname = "canvas-lms-mcp";
  version = "0.1.2-unstable";
  pyproject = true;

  src = fetchFromGitHub {
    owner = "ahnopologetic";
    repo = "canvas-lms-mcp";
    rev = "60a406140d7d8ec01b40e0fc2dad1068636a8a1b";
    hash = "sha256-UpCEXdPsQKO4hximp2l78LLh4bCm2P9SacEJQukEY3Q=";
  };

  build-system = with python313Packages; [hatchling];

  dependencies = with python313Packages; [
    fastapi
    fastmcp
    httpx
    pydantic
    uvicorn
  ];

  pythonImportsCheck = ["canvas_lms_mcp"];

  meta = {
    description = "Read-only MCP server for Canvas LMS";
    homepage = "https://github.com/ahnopologetic/canvas-lms-mcp";
    license = lib.licenses.mit;
    mainProgram = "canvas-lms-mcp";
  };
}
