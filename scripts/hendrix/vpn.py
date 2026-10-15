"""Desktop-only VPN/keyring integration; secrets stay on stdin, never argv."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import pty
import select
import termios
from pathlib import Path
import subprocess
import sys
import time

from .core import Error, STATE, atomic_json

VPN = 'vpn.ku.dk'
USER = 'fhz806'
PID = Path('/run/openconnect-hendrix.pid')
INTERFACE = 'hendrix0'
INTERFACE_PATH = Path('/sys/class/net') / INTERFACE
DNS_STATE = STATE / 'vpn.json'
ATTRIBUTES = ['application', 'hendrix', 'server', VPN, 'username', USER]


def run(args, **kwargs):
    return subprocess.run(args, **kwargs)


def ready(timeout=3):
    try:
        return run(['getent', 'ahostsv4', 'hendrixgate'], stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=timeout).returncode == 0
    except subprocess.TimeoutExpired:
        return False


def wait_ready(timeout=20):
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        if ready(timeout=min(3, remaining)):
            return True
        if not managed_pid():
            return False
        time.sleep(min(.5, max(0, deadline - time.monotonic())))


def lookup():
    # Call only during an explicit login: a locked keyring can prompt to unlock.
    result = run(['secret-tool', 'lookup', *ATTRIBUTES], capture_output=True, text=True)
    return result.stdout.rstrip('\n') if result.returncode == 0 else None


def password(action):
    if action == 'set':
        value = getpass.getpass('KUnet password (saved in GNOME keyring): ')
        if not value or '\n' in value:
            raise Error('Password must be nonempty and contain no newline.')
        result = run(['secret-tool', 'store', '--label=Hendrix KU VPN', *ATTRIBUTES],
                     input=value, text=True, stdout=subprocess.DEVNULL)
        if result.returncode:
            raise Error('Could not save to the desktop keyring.')
        print('VPN password saved. NetIQ MFA remains interactive.')
    elif action == 'forget':
        if run(['secret-tool', 'clear', *ATTRIBUTES]).returncode:
            raise Error('Could not remove the saved password (it may not exist).')
        print('Saved VPN password removed.')
    else:
        print('VPN password is saved.' if lookup() else 'No VPN password is saved (or keyring is unavailable).')


def restore_dns():
    if not DNS_STATE.exists():
        return
    state = json.loads(DNS_STATE.read_text())
    old = state.get('accept_dns')
    if old is not None:
        result = run(['sudo', 'tailscale', 'set', f'--accept-dns={str(old).lower()}'])
        if result.returncode:
            raise Error('Could not restore Tailscale DNS; retry hendrix down.')
    DNS_STATE.unlink(missing_ok=True)


def disable_dns():
    if DNS_STATE.exists():
        return  # Already changed by this helper; preserve the original value.
    if run(['systemctl', 'is-active', '--quiet', 'tailscaled.service']).returncode:
        return
    result = run(['sudo', 'tailscale', 'debug', 'prefs'], capture_output=True, text=True)
    if result.returncode:
        raise Error('Cannot read Tailscale DNS settings; refusing to change them blindly.')
    old = json.loads(result.stdout).get('CorpDNS')
    if not isinstance(old, bool):
        raise Error('Tailscale DNS preference is unavailable; no settings were changed.')
    atomic_json(DNS_STATE, {'accept_dns': old})
    if old:
        print('Temporarily disabling Tailscale DNS...')
        if run(['sudo', 'tailscale', 'set', '--accept-dns=false']).returncode:
            restore_dns()
            raise Error('Could not disable Tailscale DNS.')


def managed_pid():
    try:
        pid = int(PID.read_text().strip())
        if pid > 1 and Path(f'/proc/{pid}/comm').read_text().strip() == 'openconnect':
            return pid
    except (OSError, ValueError):
        pass
    return None


def authenticate(args, secret, terminal_path='/dev/tty'):
    """Keep stdin a terminal for OpenConnect's later interactive MFA prompts.

    stdout contains the authentication cookie and is never sent to the terminal.
    stderr remains attached so the user can see the real server prompts.
    """
    if not secret:
        return run(args, text=True, stdout=subprocess.PIPE)
    try:
        terminal = os.fdopen(os.open(terminal_path, os.O_RDWR | os.O_NOCTTY), 'r+b', buffering=0)
    except OSError as exc:
        raise Error('Saved-password VPN login needs an interactive terminal for MFA.') from exc
    master, slave = pty.openpty()
    process = None
    original = None
    try:
        original = termios.tcgetattr(terminal.fileno())
        hidden = original.copy()
        hidden[3] &= ~(termios.ECHO | termios.ECHONL)
        termios.tcsetattr(terminal.fileno(), termios.TCSANOW, hidden)
        slave_settings = termios.tcgetattr(slave)
        slave_settings[3] &= ~(termios.ECHO | termios.ECHONL)
        termios.tcsetattr(slave, termios.TCSANOW, slave_settings)
        process = subprocess.Popen([*args, '--passwd-on-stdin'], stdin=slave,
                                   stdout=subprocess.PIPE)
        os.close(slave)
        slave = None
        os.write(master, secret.encode() + b'\n')
        secret = None
        stdout = process.stdout.fileno()
        pty_open = True
        output = bytearray()
        while process.poll() is None or stdout is not None:
            sources = [terminal.fileno()]
            if stdout is not None:
                sources.append(stdout)
            if pty_open:
                sources.append(master)
            readable, _, _ = select.select(sources, [], [], .2)
            for fd in readable:
                if fd == terminal.fileno():
                    response = os.read(fd, 4096)
                    if not response:
                        raise Error('MFA input was closed; VPN login cancelled.')
                    os.write(master, response)
                elif fd == stdout:
                    chunk = os.read(fd, 4096)
                    if chunk:
                        output.extend(chunk)
                        if len(output) > 65536:
                            raise Error('Unexpectedly large authentication response.')
                    else:
                        stdout = None
                else:
                    # Never echo PTY output: it could contain a credential.
                    try:
                        if not os.read(master, 4096):
                            pty_open = False
                    except OSError:
                        pty_open = False
        return subprocess.CompletedProcess(args, process.wait(), output.decode())
    finally:
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            process.stdout.close()
        if original is not None:
            termios.tcsetattr(terminal.fileno(), termios.TCSANOW, original)
        terminal.close()
        if slave is not None:
            os.close(slave)
        os.close(master)


def up():
    if ready():
        print('KU network is reachable; keeping the existing connection.')
        return
    if managed_pid():
        raise Error('A helper-managed VPN is running but Hendrix DNS is unavailable. Check hendrix status / down.')
    if run(['sudo', '-v']).returncode:
        raise Error('VPN setup needs sudo to configure the tunnel.')
    connected = False
    try:
        disable_dns()
        if ready():
            print('KU network is reachable; no VPN connection is needed.')
            return
        print('Connecting to KU VPN. Enter the NetIQ code when prompted.')
        secret = lookup()
        args = ['openconnect', '--cookieonly', '--protocol=anyconnect', '--useragent=AnyConnect',
                '--resolve=vpn.ku.dk:130.225.226.62', '--user=' + USER]
        result = authenticate([*args, VPN], secret)
        secret = None
        if result.returncode:
            raise Error('VPN authentication failed. Update the saved password with hendrix password set '
                        'or forget it to use interactive login, then retry explicitly.')
        cookie = result.stdout.strip()
        if not cookie or '\n' in cookie:
            raise Error('VPN authentication did not return a valid cookie.')
        tunnel = run(['sudo', 'openconnect', '--background', '--pid-file=' + str(PID),
                      '--interface=' + INTERFACE, '--syslog',
                      '--protocol=anyconnect', '--useragent=AnyConnect',
                      '--resolve=vpn.ku.dk:130.225.226.62', '--cookie-on-stdin', VPN],
                     input=cookie + '\n', text=True, stdout=subprocess.DEVNULL)
        cookie = None
        if tunnel.returncode:
            raise Error('Could not establish the VPN tunnel.')
        connected = True
        if not wait_ready():
            raise Error('VPN started, but Hendrix DNS did not become available within 20 seconds. '
                        'This does not establish whether the cluster is down.')
        print('KU VPN connected. Keep it up while syncing or using SSH.')
    except BaseException:
        if connected:
            down()
            print('Failed VPN connection cleaned up; you can retry hendrix up.', file=sys.stderr)
        else:
            restore_dns()
        raise


def down():
    pid = managed_pid()
    if pid:
        print('Disconnecting helper-managed VPN...')
        if run(['sudo', 'kill', '-INT', str(pid)]).returncode:
            raise Error('Could not stop the VPN.')
        # Wait for the network cleanup, so it cannot overwrite restored DNS later.
        for _ in range(50):
            if not Path(f'/proc/{pid}').exists():
                break
            time.sleep(.1)
        else:
            raise Error('VPN has not stopped yet; retry hendrix down to restore DNS.')
    else:
        print('No helper-managed VPN is running.')
    if PID.exists():
        run(['sudo', 'rm', '-f', '--', str(PID)], check=True)
    # Use a dedicated interface so stale DNS can be removed without touching
    # another VPN. Only remove it after the tunnel has disappeared.
    if not INTERFACE_PATH.exists():
        if run(['sudo', 'resolvconf', '-d', INTERFACE]).returncode:
            raise Error('Could not remove VPN DNS settings; retry hendrix down.')
    restore_dns()
    print('Previous Tailscale DNS preference restored.')


def main():
    parser = argparse.ArgumentParser(prog='hendrix-vpn', description=__doc__)
    parser.add_argument('action', choices=['up', 'down', 'status', 'password'])
    parser.add_argument('password_action', nargs='?', choices=['set', 'forget', 'status'], default='status')
    args = parser.parse_args()
    try:
        if args.action == 'password':
            password(args.password_action)
        elif args.action == 'up':
            up()
        elif args.action == 'down':
            down()
        else:
            print('Hendrix network: ' + ('reachable' if ready() else 'unavailable'))
            print('Helper VPN: ' + (f'running (PID {managed_pid()})' if managed_pid() else 'not running'))
    except (Error, OSError, subprocess.SubprocessError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('Cancelled.', file=sys.stderr)
        return 130
    return 0


if __name__ == '__main__':
    sys.exit(main())
