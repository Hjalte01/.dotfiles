"""Install a reproducible interactive shell in the user's own cluster account."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess

from .core import Error


# Hendrix's system Python is 3.6; keep this embedded installer compatible.
REMOTE_INSTALL = r'''
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

payload = json.load(sys.stdin)
if platform.machine() != 'x86_64':
    sys.exit('The packaged zoxide binary requires an x86_64 cluster host.')
binary = base64.b64decode(payload['zoxide'], validate=True)
if hashlib.sha256(binary).hexdigest() != payload['sha256']:
    sys.exit('zoxide checksum mismatch; shell configuration was not changed.')
home = Path.home()
config = home / '.config/hendrix'
config.mkdir(parents=True, exist_ok=True)
stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')

def write(path, data, executable=False, backup=False):
    if path.exists() and path.read_bytes() == data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = 0o755 if executable else (path.stat().st_mode & 0o777 if path.exists() else 0o644)
    if backup and path.exists():
        backups = config / 'backups'
        backups.mkdir(exist_ok=True)
        saved = backups / (path.name + '.' + stamp)
        shutil.copy2(str(path), str(saved))
        print('Backup: ' + str(saved))
    fd, temporary = tempfile.mkstemp(dir=str(path.parent), prefix='.hendrix-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.chmod(temporary, mode)
        os.replace(temporary, str(path))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

# Install terminal capabilities before activating the shell configuration.
terminfo = home / '.terminfo'
terminfo.mkdir(exist_ok=True)
subprocess.run(['tic', '-x', '-o', str(terminfo), '-'],
               input=payload['terminfo'], universal_newlines=True, check=True)
zoxide = home / '.local/bin/zoxide'
write(zoxide, binary, executable=True)
subprocess.run([str(zoxide), '--version'], check=True)
write(config / 'shell.bash', payload['shell'].encode('utf-8'))
hook = """
# BEGIN hendrix shell-setup
if [ -n "${BASH_VERSION:-}" ]; then
    case $- in
        *i*) [ ! -r "$HOME/.config/hendrix/shell.bash" ] || . "$HOME/.config/hendrix/shell.bash" ;;
    esac
fi
# END hendrix shell-setup
"""
login = next((home / name for name in ('.bash_profile', '.bash_login', '.profile')
              if (home / name).exists()), home / '.bash_profile')
for path in (home / '.bashrc', login):
    previous = path.read_text() if path.exists() else ''
    if '# BEGIN hendrix shell-setup' not in previous:
        separator = '' if not previous or previous.endswith('\n') else '\n'
        write(path, (previous + separator + hook).encode('utf-8'), backup=True)
project = Path(os.path.expanduser(payload['project']))
if project.is_dir():
    subprocess.run([str(zoxide), 'add', '--', str(project)], check=True)
    print('Registered project: ' + str(project))
print('Installed terminal capabilities and interactive Bash configuration.')
'''


def install_shell(backend):
    asset = os.environ.get('HENDRIX_REMOTE_ZOXIDE')
    if not asset:
        raise Error('The packaged zoxide asset is unavailable. Rebuild the Hendrix Nix package first.')
    binary = Path(asset).read_bytes()
    terminfo = subprocess.run(['infocmp', '-x', 'xterm-ghostty'],
                             capture_output=True, text=True, check=True).stdout
    payload = dict(zoxide=base64.b64encode(binary).decode('ascii'),
                   sha256=hashlib.sha256(binary).hexdigest(), terminfo=terminfo,
                   shell=Path(__file__).with_name('shell.bash').read_text(),
                   project=backend.profile.remote)
    result = subprocess.run(backend.ssh_argv('python3 -c ' + shlex.quote(REMOTE_INSTALL)),
                            input=json.dumps(payload), capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise Error((result.stderr or result.stdout or 'Remote shell setup failed.').strip())
    print(result.stdout.strip())
    print('Open a new Hendrix SSH session to use the updated shell; try: cd mean')
