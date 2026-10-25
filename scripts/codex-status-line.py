"""Keep Codex's directory status compact while preserving its writable config."""
import os
from pathlib import Path
import shutil

import tomlkit


path = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'config.toml'
previous = path.read_text() if path.exists() else ''
document = tomlkit.parse(previous)
tui = document.setdefault('tui', tomlkit.table())
items = tui.get('status_line')
if items is None:
    tui['status_line'] = [
        'model-with-reasoning', 'project-name', 'context-used',
        'five-hour-limit', 'weekly-limit', 'permissions',
    ]
else:
    # Change only the directory item, retaining order, comments and formatting.
    for index, item in enumerate(items):
        if item == 'current-dir':
            items[index] = 'project-name'

updated = tomlkit.dumps(document)
if updated != previous:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_name('config.toml.before-compact-status-line')
    if path.exists() and not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(updated)
