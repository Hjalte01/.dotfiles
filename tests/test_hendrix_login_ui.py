"""Offline regression tests for handing terminal control back after login."""
from contextlib import contextmanager
import subprocess
import unittest
from unittest.mock import Mock, patch

from hendrix.app import HendrixApp
from hendrix.core import Error


class ForegroundTerminal:
    """Model Textual's suspend context, whose resume follows yield without finally."""

    def __init__(self):
        self.busy = False
        self.refreshing = False
        self.suspended = False
        self.events = []
        self.backend = Mock()

    @contextmanager
    def suspend(self):
        self.suspended = True
        self.events.append(('suspend',))
        yield
        self.suspended = False
        self.events.append(('resume',))

    def output(self, text):
        assert not self.suspended, 'Output attempted before terminal resumed'
        self.events.append(('output', text))

    def notify(self, text, **kwargs):
        assert not self.suspended, 'Notification attempted before terminal resumed'
        self.events.append(('notify', text, kwargs))

    def refresh_data(self, **kwargs):
        assert not self.suspended, 'Refresh attempted before terminal resumed'
        assert not self.busy, 'Refresh attempted before operation finished'
        self.events.append(('refresh', kwargs))


class ForegroundLoginTests(unittest.IsolatedAsyncioTestCase):
    async def run_foreground(self, terminal, action):
        # Call the worker body directly so a real terminal, SSH and VPN are unused.
        await HendrixApp.foreground.__wrapped__(terminal, action)

    async def test_login_failures_resume_before_reporting_without_refresh(self):
        for error in (Error('Password rejected'), OSError('SSH unavailable'),
                      subprocess.TimeoutExpired(['ssh', 'hendrix'], 15),
                      RuntimeError('Unexpected authentication error')):
            with self.subTest(error=type(error).__name__):
                terminal = ForegroundTerminal()
                with patch('hendrix.app.connect', side_effect=error):
                    await self.run_foreground(terminal, 'connect')
                self.assertEqual(terminal.events[:3], [
                    ('suspend',), ('resume',), ('output', str(error))])
                self.assertEqual(terminal.events[3],
                    ('notify', str(error), {'severity': 'error', 'timeout': 10}))
                self.assertEqual(len(terminal.events), 4)
                self.assertFalse(terminal.busy)
                self.assertFalse(terminal.suspended)

    async def test_cancelled_login_resumes_and_keeps_tui_running(self):
        terminal = ForegroundTerminal()
        with patch('hendrix.app.connect', side_effect=KeyboardInterrupt):
            await self.run_foreground(terminal, 'connect')
        self.assertEqual(terminal.events, [
            ('suspend',), ('resume',), ('output', 'connect: cancelled'),
            ('notify', 'connect: cancelled', {'severity': 'warning'})])
        self.assertFalse(terminal.busy)
        self.assertFalse(terminal.suspended)

    async def test_successful_login_resumes_before_completion_and_refresh(self):
        terminal = ForegroundTerminal()
        with patch('hendrix.app.connect', side_effect=lambda backend:
                   terminal.events.append(('connect', backend))):
            await self.run_foreground(terminal, 'connect')
        self.assertEqual(terminal.events, [
            ('suspend',), ('connect', terminal.backend), ('resume',),
            ('output', 'connect: completed'), ('refresh', {'force': True})])
        self.assertFalse(terminal.busy)

    async def test_terminal_command_runs_suspended_then_refreshes_connection(self):
        terminal = ForegroundTerminal()
        terminal.backend.ssh_argv.return_value = ['ssh', 'hendrix']
        with patch('hendrix.app.connect') as connect, \
             patch('hendrix.app.subprocess.run', side_effect=lambda argv:
                   terminal.events.append(('terminal', argv))):
            await self.run_foreground(terminal, 'terminal')
        connect.assert_called_once_with(terminal.backend)
        terminal.backend.ssh_argv.assert_called_once_with(batch=False)
        self.assertEqual(terminal.events, [
            ('suspend',), ('terminal', ['ssh', 'hendrix']), ('resume',),
            ('output', 'terminal: completed'), ('refresh', {'force': True})])

    async def test_terminal_failure_after_login_resumes_and_refreshes_connection(self):
        for error in (subprocess.TimeoutExpired(['ssh', 'hendrix'], 15), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                terminal = ForegroundTerminal()
                with patch('hendrix.app.connect'), \
                     patch('hendrix.app.subprocess.run', side_effect=error):
                    await self.run_foreground(terminal, 'terminal')
                self.assertEqual(terminal.events[:2], [('suspend',), ('resume',)])
                self.assertEqual(terminal.events[-1], ('refresh', {'force': True}))
                self.assertFalse(terminal.busy)
                self.assertFalse(terminal.suspended)
                messages = [event[1] for event in terminal.events if event[0] == 'output']
                self.assertEqual(messages, ['terminal: cancelled' if isinstance(error, KeyboardInterrupt)
                                            else str(error)])

    async def test_backend_error_preparing_terminal_command_resumes(self):
        terminal = ForegroundTerminal()
        terminal.backend.ssh_argv.side_effect = OSError('Missing SSH executable')
        with patch('hendrix.app.connect'), patch('hendrix.app.subprocess.run') as run:
            await self.run_foreground(terminal, 'terminal')
        run.assert_not_called()
        self.assertEqual(terminal.events[:3], [
            ('suspend',), ('resume',), ('output', 'Missing SSH executable')])
        self.assertEqual(terminal.events[-1], ('refresh', {'force': True}))

    async def test_failed_editor_does_not_reload_profiles_or_report_completion(self):
        terminal = ForegroundTerminal()
        with patch('hendrix.app.edit_profiles', side_effect=Error('Editor failed')), \
             patch('hendrix.app.load_profiles') as load:
            await self.run_foreground(terminal, 'edit')
        load.assert_not_called()
        self.assertEqual(terminal.events[:3], [
            ('suspend',), ('resume',), ('output', 'Editor failed')])
        self.assertEqual(len(terminal.events), 4)
        self.assertFalse(terminal.busy)


if __name__ == '__main__':
    unittest.main()
