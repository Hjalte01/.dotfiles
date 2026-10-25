"""Offline authenticator tests using public RFC test data; no real keyring reads."""
import os
import hashlib
import pty
import subprocess
import sys
import termios
import unittest
from unittest.mock import patch

from hendrix import vpn


SEED = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'


class TOTPTests(unittest.TestCase):
    def test_provisioning_validation(self):
        self.assertEqual(vpn.parse_totp(SEED.lower()), SEED)
        self.assertEqual(vpn.parse_totp(f'otpauth://totp/KU:user?secret={SEED}&issuer=KU'), SEED)
        for value in ['123456', 'https://enroll.example/private-token',
                      'otpauth://hotp/KU?secret=' + SEED,
                      f'otpauth://totp/KU?secret={SEED}&digits=8',
                      f'otpauth://totp/KU?secret={SEED}&period=60',
                      f'otpauth://totp/KU?secret={SEED}&algorithm=SHA256',
                      f'otpauth://totp/KU?secret={SEED}&secret={SEED}']:
            with self.subTest(value=value), self.assertRaises(vpn.Error) as error:
                vpn.parse_totp(value)
            self.assertNotIn(SEED, str(error.exception))

    def test_token_keyring_cannot_match_password_lookup(self):
        def attributes(items):
            return dict(zip(items[::2], items[1::2]))
        password = attributes(vpn.ATTRIBUTES)
        token = attributes(vpn.TOTP_ATTRIBUTES)
        self.assertTrue(any(token.get(k) != v for k, v in password.items()))

    def test_qr_import_stores_privately_and_does_not_echo_seed(self):
        import io
        output = io.StringIO()
        def run(args, **kwargs):
            if args[0] == 'zbarimg':
                return subprocess.CompletedProcess(args, 0, f'otpauth://totp/KU?secret={SEED}\n')
            self.assertEqual(args[:2], ['secret-tool', 'store'])
            self.assertNotIn(SEED, repr(args))
            self.assertEqual(kwargs['input'], SEED)
            return subprocess.CompletedProcess(args, 0)
        with patch.object(vpn, 'run', side_effect=run), patch.object(vpn.sys, 'stdout', output):
            vpn.totp('import', '/private/qr.png')
        self.assertNotIn(SEED, output.getvalue())

    def test_password_and_token_reach_child_without_secrets_in_argv(self):
        master, slave = pty.openpty()
        original = termios.tcgetattr(slave)
        program = f'''import os, sys, hashlib
password = sys.stdin.readline().strip().encode()
assert hashlib.sha256(password).hexdigest() == '{hashlib.sha256(b'test-password').hexdigest()}'
assert '--token-mode=totp' in sys.argv
path = next(a.split('@', 1)[1] for a in sys.argv if a.startswith('--token-secret=@'))
token = open(path, 'rb').read()
assert hashlib.sha256(token).hexdigest() == '{hashlib.sha256(('base32:' + SEED).encode()).hexdigest()}'
cmdline = open('/proc/self/cmdline', 'rb').read()
assert password not in cmdline
assert token not in cmdline
print('test-cookie')
'''
        try:
            result = vpn.authenticate([sys.executable, '-c', program], 'test-password',
                                      os.ttyname(slave), token=SEED)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), 'test-cookie')
            self.assertNotIn(SEED, repr(result.args[3:]))
            self.assertEqual(termios.tcgetattr(slave), original)
        finally:
            os.close(master)
            os.close(slave)

    def test_anonymous_seed_file_is_closed_after_failure(self):
        with self.assertRaisesRegex(RuntimeError, 'fake failure'):
            with vpn.token_options(SEED) as (_, fds):
                fd = fds[0]
                raise RuntimeError('fake failure')
        with self.assertRaises(OSError):
            os.fstat(fd)

    def test_native_openconnect_accepts_anonymous_seed_file(self):
        # Connection-refused on loopback proves OpenConnect parsed the token
        # before networking; no account or external VPN is contacted.
        import socket
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
            with vpn.token_options(SEED) as (args, fds):
                result = subprocess.run(['openconnect', *args, '--non-inter', '--cookieonly',
                                         f'https://127.0.0.1:{port}'], pass_fds=fds,
                                        capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Failed to connect', result.stderr)
        self.assertNotIn('Invalid', result.stderr)
        self.assertNotIn(SEED, result.stderr + result.stdout)


if __name__ == '__main__':
    unittest.main()
