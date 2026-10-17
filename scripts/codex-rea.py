"""Register the Nix-managed REA runtime and skill, preserving Codex settings."""

from pathlib import Path
import shutil
import sys

import tomlkit


package = Path(sys.argv[1])
home = Path.home()
path = home / ".codex/config.toml"
previous = path.read_text() if path.exists() else ""
document = tomlkit.parse(previous)
servers = document.setdefault("mcp_servers", tomlkit.table())
server = servers.setdefault("rea", tomlkit.table())
# Nix's full Node package links to nodejs-slim. REA's diagnostics compare this
# command against process.execPath, which contains the resolved binary path.
server["command"] = str(Path(sys.argv[2]).resolve())
server["args"] = [str(package / "lib/node_modules/rea-agents/scripts/rea.mjs"), "mcp"]
server["startup_timeout_sec"] = 30
updated = tomlkit.dumps(document)
if updated != previous:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_name("config.toml.before-nix-rea")
    if path.exists() and not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(updated)

# REA's skill diagnostics require regular files instead of Home Manager links.
# Copy the pinned bundle on activation; leave other skills untouched.
source = package / "lib/node_modules/rea-agents/skills/reverse-engineer-anything"
destination = home / ".agents/skills/reverse-engineer-anything"
for original in source.rglob("*"):
    if not original.is_file():
        continue
    target = destination / original.relative_to(source)
    if target.exists() and target.read_bytes() == original.read_bytes():
        continue
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        backup = target.with_name(target.name + ".before-nix-rea")
        if not backup.exists():
            shutil.copy2(target, backup)
    shutil.copyfile(original, target)
    target.chmod(0o644)
