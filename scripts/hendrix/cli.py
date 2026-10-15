"""Local Hendrix commands. Running the TUI does not connect automatically."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

from .core import Backend, CONFIG, Error, load_profiles


def vpn(action, extra=()):
    command = shutil.which('hendrix-vpn')
    if not command:
        raise Error('Desktop VPN helper is unavailable on this host. Connect to the KU network separately.')
    if subprocess.run([command, action, *extra]).returncode:
        raise Error('VPN action did not complete.')


def connect(backend):
    if backend.profile.host == 'hendrix' and shutil.which('hendrix-vpn'):
        vpn('up')
    backend.connect()


def setup_ssh(backend):
    config = subprocess.run(['ssh', '-G', backend.profile.host], capture_output=True, text=True, check=True)
    candidates = [Path(line.split(' ', 1)[1]).expanduser() for line in config.stdout.splitlines()
                  if line.startswith('identityfile ')]
    public = next((Path(str(p) + '.pub') for p in candidates if Path(str(p) + '.pub').is_file()), None)
    if public is None:
        raise Error('No public key matches your SSH configuration. Create/configure a key first; existing keys are preserved.')
    print(f'Installing public key {public} using your normal account login.')
    print('This only updates your own ~/.ssh/authorized_keys on Hendrix.')
    if subprocess.run(['ssh-copy-id', '-i', str(public), backend.profile.host]).returncode:
        raise Error('SSH key installation failed; keep using interactive session reuse.')
    # Disable the existing control session to actually test key authentication.
    check = subprocess.run(['ssh', '-o', 'ControlMaster=no', '-o', 'ControlPath=none',
                            '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', backend.profile.host, 'true'])
    if check.returncode:
        raise Error('The key was copied but authentication did not succeed. An encrypted key may need ssh-add; '
                    'otherwise use session reuse rather than changing server settings.')
    print('SSH key authentication works.')


def edit_profiles():
    if not (CONFIG / 'profiles.json').exists():
        load_profiles()  # Allow the editor to repair an existing invalid file.
    editor = shlex.split(os.environ.get('EDITOR', 'nvim'))
    subprocess.run([*editor, str(CONFIG / 'profiles.json')], check=True)
    load_profiles()  # Report invalid edits without overwriting the file.


def main():
    parser = argparse.ArgumentParser(prog='hendrix', description=__doc__)
    parser.add_argument('--project', help='Saved project name (defaults to first project)')
    parser.add_argument('action', nargs='?', default='ssh',
                        choices=['tui', 'up', 'down', 'status', 'password', 'ssh', 'connect', 'setup-ssh', 'profiles', 'reconcile', 'resolve'])
    args, extra = parser.parse_known_args()
    try:
        if args.action in ('up', 'down', 'status', 'password'):
            vpn(args.action, extra)
            return 0
        if args.action == 'profiles':
            edit_profiles()
            return 0
        if args.action == 'tui':
            from .app import HendrixApp
            HendrixApp(project=args.project).run()
            return 0
        profiles = load_profiles()
        profile = next((p for p in profiles if p.name == args.project), None) if args.project else profiles[0]
        if profile is None:
            raise Error(f'Unknown project: {args.project}')
        backend = Backend(profile)
        if args.action == 'reconcile':
            print(backend.reconcile())
        elif args.action == 'resolve':
            resolve_parser = argparse.ArgumentParser(prog='hendrix resolve')
            resolve_parser.add_argument('token')
            group = resolve_parser.add_mutually_exclusive_group(required=True)
            group.add_argument('--job-id')
            group.add_argument('--not-submitted', action='store_true')
            resolution = resolve_parser.parse_args(extra)
            if resolution.not_submitted:
                print('Only proceed if you have checked that Slurm did not accept this submission.')
                if input('Type the submission token to confirm: ').strip() != resolution.token:
                    raise Error('Confirmation did not match; nothing changed.')
            print(backend.resolve(resolution.token, resolution.job_id, resolution.not_submitted))
        elif args.action == 'setup-ssh':
            if profile.host == 'hendrix' and shutil.which('hendrix-vpn'):
                vpn('up')
            setup_ssh(backend)
        else:
            connect(backend)
            if args.action == 'ssh':
                return subprocess.run(backend.ssh_argv(batch=False) + extra).returncode
    except (Error, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == '__main__':
    sys.exit(main())
