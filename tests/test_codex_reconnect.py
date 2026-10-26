"""Keep the resume workaround confined to verified Codex internet sockets."""

from contextlib import redirect_stdout
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'codex-reconnect.py'
SPEC = importlib.util.spec_from_file_location('codex_reconnect', SCRIPT)
reconnect = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reconnect)


def row(peer='172.64.155.209:443', local='192.168.0.157:38946', state='ESTAB'):
    return (f'{state} 0 240 {local} {peer} '
            'users:(("codex",pid=22134,fd=29)) timer:(on,53sec,8) '
            'uid:1000 ino:2009898 sk:6 cgroup:/user.slice/user-1000.slice/app.scope <->')


class ReconnectTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.proc = Path(self.directory.name)
        self.process = self.proc / '22134'
        (self.process / 'fd').mkdir(parents=True)
        (self.process / 'exe').symlink_to('/nix/store/example/bin/codex')
        (self.process / 'fd' / '29').symlink_to('socket:[2009898]')
        (self.process / 'cgroup').write_text('0::/user.slice/user-1000.slice/app.scope\n')

    def candidates(self, line):
        return list(reconnect.connections(line, self.proc))

    def test_real_ss_output_and_exact_reset_filter(self):
        connection, = self.candidates(row())
        self.assertEqual(reconnect.reset_command('/bin/ss', connection), [
            '/bin/ss', '-K', '-t', '-4',
            'src 192.168.0.157 sport = :38946 dst 172.64.155.209 dport = :443'])

    def test_unrelated_executable_cannot_spoof_ss_process_label(self):
        (self.process / 'exe').unlink()
        (self.process / 'exe').symlink_to('/nix/store/example/bin/firefox')
        self.assertEqual(self.candidates(row()), [])

    def test_inode_must_still_match_descriptor(self):
        (self.process / 'fd' / '29').unlink()
        (self.process / 'fd' / '29').symlink_to('socket:[9999]')
        self.assertEqual(self.candidates(row()), [])

    def test_only_frozen_user_slice_processes_are_eligible(self):
        (self.process / 'cgroup').write_text('0::/system.slice/example.service\n')
        self.assertEqual(self.candidates(row()), [])

    def test_nonpublic_peers_and_other_ports_are_preserved(self):
        for peer in ['127.0.0.1:443', '10.0.0.1:443', '100.64.0.1:443',
                     '[::1]:443', '[fd00::1]:443', '[::ffff:127.0.0.1]:443',
                     '[::ffff:192.168.1.2]:443', '172.64.155.209:80']:
            with self.subTest(peer=peer):
                self.assertEqual(self.candidates(row(peer)), [])

    def test_ipv6_uses_ipv6_filter(self):
        connection, = self.candidates(row('[2606:4700:4400::ac40:9bd1]:443',
                                           '[2001:4860:4860::8844]:38946'))
        self.assertEqual(connection.family, '-6')
        self.assertEqual(reconnect.reset_command('/bin/ss', connection)[-1],
                         'src [2001:4860:4860::8844] sport = :38946 '
                         'dst [2606:4700:4400::ac40:9bd1] dport = :443')

    def test_missing_owner_inode_and_nonestablished_rows_are_ignored(self):
        for line in [row(state='SYN-SENT'), row().replace('ino:2009898', ''),
                     row().replace('pid=22134,fd=29', ''), 'malformed']:
            with self.subTest(line=line):
                self.assertEqual(self.candidates(line), [])

    def test_apply_does_not_even_list_sockets_when_users_are_not_frozen(self):
        with patch.object(reconnect, 'users_frozen', return_value=False), \
                patch.object(reconnect.subprocess, 'run') as run, \
                redirect_stdout(io.StringIO()):
            self.assertEqual(reconnect.main(['--ss', '/bin/ss', '--apply']), 0)
        run.assert_not_called()

    def test_dry_run_never_resets_sockets(self):
        connection, = self.candidates(row())
        listing = subprocess.CompletedProcess([], 0, stdout=row(), stderr='')
        with patch.object(reconnect.subprocess, 'run', return_value=listing) as run, \
                patch.object(reconnect, 'connections', return_value=[connection]), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(reconnect.main(['--ss', '/bin/ss']), 0)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], ['/bin/ss', '-Htnpe', '( dport = :443 )'])

    def test_apply_rechecks_owner_and_freeze_before_reset(self):
        connection, = self.candidates(row())
        listing = subprocess.CompletedProcess([], 0, stdout=row(), stderr='')
        with patch.object(reconnect.subprocess, 'run', return_value=listing) as run, \
                patch.object(reconnect, 'connections', return_value=[connection]), \
                patch.object(reconnect, 'users_frozen', return_value=True), \
                patch.object(reconnect, 'owned_by_codex', return_value=True) as owner, \
                redirect_stdout(io.StringIO()):
            self.assertEqual(reconnect.main(['--ss', '/bin/ss', '--apply']), 0)
        owner.assert_called_once_with(connection)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args.args[0], reconnect.reset_command('/bin/ss', connection))
        self.assertEqual(run.call_args.kwargs['timeout'], 3)

    def test_unexpected_thaw_stops_all_resets(self):
        connection, = self.candidates(row())
        listing = subprocess.CompletedProcess([], 0, stdout=row(), stderr='')
        with patch.object(reconnect.subprocess, 'run', return_value=listing) as run, \
                patch.object(reconnect, 'connections', return_value=[connection]), \
                patch.object(reconnect, 'users_frozen', side_effect=[True, False]), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(reconnect.main(['--ss', '/bin/ss', '--apply']), 1)
        self.assertEqual(run.call_count, 1)


if __name__ == '__main__':
    unittest.main()
