"""Desktop-only VPN/keyring integration; secrets stay on stdin, never argv."""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import getpass
import os
import pty
import re
import select
import termios
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import parse_qs, urlsplit

from .core import Error

VPN = 'vpn.ku.dk'
USER = 'fhz806'
PID = Path('/run/openconnect-hendrix.pid')
INTERFACE = 'hendrix0'
ATTRIBUTES = ['application', 'hendrix', 'server', VPN, 'username', USER]
# secret-tool matches subsets: a different application prevents the existing
# password lookup from accidentally selecting the TOTP entry.
TOTP_ATTRIBUTES = ['application', 'hendrix-totp', 'server', VPN, 'username', USER]


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
    try:
        result = run(['secret-tool', 'lookup', *ATTRIBUTES], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None  # Let the explicit login use the normal terminal password prompt.
    return result.stdout.rstrip('\n') if result.returncode == 0 else None


def parse_totp(value):
    """Accept ordinary authenticator provisioning; never include input in errors."""
    value = value.strip()
    if value.startswith('otpauth:'):
        uri = urlsplit(value)
        params = parse_qs(uri.query)
        if (uri.scheme != 'otpauth' or uri.netloc != 'totp'
                or any(len(v) != 1 for v in params.values())
                or params.get('algorithm', ['SHA1'])[0].upper() != 'SHA1'
                or params.get('digits', ['6'])[0] != '6'
                or params.get('period', ['30'])[0] != '30'):
            raise Error('Only SHA1 TOTP with six digits and a 30-second period is supported.')
        value = params.get('secret', [''])[0]
    value = re.sub(r'[\s-]', '', value).upper().rstrip('=')
    try:
        if not re.fullmatch(r'[A-Z2-7]{16,208}', value):
            raise ValueError
        decoded = base64.b32decode(value + '=' * (-len(value) % 8))
        if not 10 <= len(decoded) <= 128:
            raise ValueError
    except ValueError:
        raise Error('Invalid TOTP secret. Use the Base32 setup key or an otpauth://totp URI.') from None
    return value


def lookup_totp():
    try:
        result = run(['secret-tool', 'lookup', *TOTP_ATTRIBUTES], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode or not result.stdout:
        return None
    return parse_totp(result.stdout)


def totp(action, image=None):
    if action in ('set', 'import'):
        if action == 'import':
            if not image:
                raise Error('Usage: hendrix totp import /path/to/authenticator-qr.png')
            result = run(['zbarimg', '--quiet', '--raw', '--', image], capture_output=True, text=True, timeout=20)
            if result.returncode or len(result.stdout.splitlines()) != 1:
                raise Error('Could not read exactly one authenticator QR code from that image.')
            value = result.stdout.strip()
        else:
            value = getpass.getpass('TOTP setup key or otpauth URI (hidden): ')
        value = parse_totp(value)
        if run(['secret-tool', 'store', '--label=Hendrix VPN TOTP', *TOTP_ATTRIBUTES],
               input=value, text=True, stdout=subprocess.DEVNULL).returncode:
            raise Error('Could not save TOTP to the desktop keyring.')
        print('TOTP saved in the desktop keyring. New VPN logins will generate codes automatically.')
    elif action == 'forget':
        if run(['secret-tool', 'clear', *TOTP_ATTRIBUTES]).returncode:
            raise Error('Could not remove the saved TOTP secret (it may not exist).')
        print('TOTP secret removed. New VPN logins will ask for the code.')
    else:
        print('TOTP is saved.' if lookup_totp() else 'No TOTP secret is available; codes remain interactive.')


@contextmanager
def token_options(token):
    if not token:
        yield [], ()
        return
    # OpenConnect accepts @filename. An inherited anonymous RAM file keeps the
    # seed out of argv, environment variables and persistent temporary files.
    fd = os.memfd_create('hendrix-totp', os.MFD_CLOEXEC)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, ('base32:' + parse_totp(token)).encode())
        os.lseek(fd, 0, os.SEEK_SET)
        yield ['--token-mode=totp', f'--token-secret=@/proc/self/fd/{fd}'], (fd,)
    finally:
        os.close(fd)


def password(action):
    if action == 'set':
        value = getpass.getpass('KUnet password (saved in GNOME keyring): ')
        if not value or '\n' in value:
            raise Error('Password must be nonempty and contain no newline.')
        result = run(['secret-tool', 'store', '--label=Hendrix KUnet (VPN + SSH)', *ATTRIBUTES],
                     input=value, text=True, stdout=subprocess.DEVNULL)
        if result.returncode:
            raise Error('Could not save to the desktop keyring.')
        print('KUnet password saved for Hendrix VPN and SSH.')
    elif action == 'forget':
        if run(['secret-tool', 'clear', *ATTRIBUTES]).returncode:
            raise Error('Could not remove the saved password (it may not exist).')
        print('Saved KUnet password removed.')
    else:
        print('KUnet password is saved for Hendrix VPN and SSH.' if lookup() else 'No KUnet password is saved (or keyring is unavailable).')


def ssh_askpass(prompt):
    """OpenSSH consumes stdout privately; never invoke this through a log.

    Share the existing KUnet entry with only the matching SSH account. Reject
    host-key, key-passphrase, MFA and unexpected-account prompts. --check
    reports availability using only an exit status.
    """
    allowed = re.fullmatch(r"fhz806@hendrixgate(?:\.science\.ku\.dk)?'s password:\s*", prompt)
    if prompt != '--check' and not allowed:
        return 1
    secret = lookup()
    if not secret or any(c in secret for c in '\n\r\x00'):
        return 1
    if prompt != '--check':
        sys.stdout.write(secret + '\n')
        sys.stdout.flush()
    return 0


def managed_pid():
    try:
        pid = int(PID.read_text().strip())
        if pid > 1 and Path(f'/proc/{pid}/comm').read_text().strip() == 'openconnect':
            return pid
    except (OSError, ValueError):
        pass
    return None


def authenticate(args, secret, terminal_path='/dev/tty', token=None):
    with token_options(token) as (options, fds):
        return _authenticate([*args, *options], secret, terminal_path, fds)


def _authenticate(args, secret, terminal_path, fds):
    """Keep stdin a terminal for OpenConnect's later interactive MFA prompts.

    stdout contains the authentication cookie and is never sent to the terminal.
    stderr remains attached so the user can see the real server prompts.
    """
    if not secret:
        return run(args, text=True, stdout=subprocess.PIPE, pass_fds=fds)
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
                                   stdout=subprocess.PIPE, pass_fds=fds)
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
        # A tunnel may be reconnecting after sleep or a network switch. Give its
        # DNS a bounded grace period before replacing only our own tunnel.
        print('Waiting for the existing KU VPN…')
        if wait_ready(timeout=5):
            print('KU VPN is reachable; keeping the existing connection.')
            return
        print('KU VPN has stale DNS; restarting the helper-managed tunnel…')
        down()
        if ready():
            print('KU network is reachable after VPN cleanup.')
            return
    if run(['systemctl', 'is-active', '--quiet', 'systemd-resolved.service']).returncode:
        raise Error('KU VPN needs systemd-resolved for DNS alongside Tailscale. '
                    'Activate the desktop NixOS configuration with nxb, then retry hendrix up.')
    if run(['sudo', '-v']).returncode:
        raise Error('VPN setup needs sudo to configure the tunnel.')
    connected = False
    try:
        token = lookup_totp()
        print('Connecting to KU VPN. ' + ('Using saved TOTP authenticator.' if token
                                         else 'Enter the NetIQ code when prompted.'))
        secret = lookup()
        args = ['openconnect', '--cookieonly', '--protocol=anyconnect', '--useragent=AnyConnect',
                '--resolve=vpn.ku.dk:130.225.226.62', '--user=' + USER]
        result = authenticate([*args, VPN], secret, token=token)
        secret = None
        token = None
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
        raise


def down():
    pid = managed_pid()
    if pid:
        print('Disconnecting helper-managed VPN...')
        if run(['sudo', 'kill', '-INT', str(pid)]).returncode:
            raise Error('Could not stop the VPN.')
        # OpenConnect's vpnc-script removes only this link's resolved settings.
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
    # resolved also drops per-link DNS automatically when the tunnel disappears.
    print('KU VPN disconnected. Tailscale DNS remains available.')


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--ssh-askpass':
        try:
            return ssh_askpass(sys.argv[2])
        except (Error, OSError, subprocess.SubprocessError):
            return 1
    parser = argparse.ArgumentParser(prog='hendrix-vpn', description=__doc__)
    parser.add_argument('action', choices=['up', 'down', 'status', 'password', 'totp'])
    parser.add_argument('credential_action', nargs='?', choices=['set', 'import', 'forget', 'status'], default='status')
    parser.add_argument('image', nargs='?')
    args = parser.parse_args()
    try:
        if args.action == 'password':
            if args.credential_action == 'import' or args.image:
                raise Error('Usage: hendrix password [set|forget|status]')
            password(args.credential_action)
        elif args.action == 'totp':
            totp(args.credential_action, args.image)
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
