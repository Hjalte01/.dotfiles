"""Dashboard startup, VPN recovery and persisted table controls."""
from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from hendrix import cli, core, vpn
from hendrix.app import (HendrixApp, ColumnChooser, TABLE_COLUMNS, COMPACT_COLUMNS,
                         availability_bar, load_columns)
from textual.widgets import DataTable, Select, SelectionList, Static


class StartupTests(unittest.TestCase):
    def test_cli_authenticates_before_running_tui_and_keeps_failures_reviewable(self):
        for failure in (None, core.Error('VPN unavailable'), KeyboardInterrupt()):
            with self.subTest(failure=failure):
                events = []
                app = Mock(startup_connected=False, startup_error=None)
                app.run.side_effect = lambda: events.append('tui')
                def connect(backend):
                    events.append('login')
                    self.assertIs(backend, app.backend)
                    if failure:
                        raise failure
                with patch('hendrix.app.HendrixApp', return_value=app), \
                     patch.object(cli, 'connect', side_effect=connect), \
                     patch('sys.argv', ['hendrix', 'tui']):
                    self.assertEqual(cli.main(), 0)
                self.assertEqual(events, ['login', 'tui'])
                self.assertEqual(app.startup_connected, failure is None)
                self.assertEqual(app.startup_error is None, failure is None)

    def test_recovering_tunnel_is_reused_without_authentication(self):
        with patch.object(vpn, 'ready', return_value=False), \
             patch.object(vpn, 'managed_pid', return_value=123), \
             patch.object(vpn, 'wait_ready', return_value=True) as wait, \
             patch.object(vpn, 'down') as down, patch.object(vpn, 'authenticate') as auth:
            vpn.up()
        wait.assert_called_once_with(timeout=5)
        down.assert_not_called()
        auth.assert_not_called()

    def test_stale_tunnel_restarts_once_and_failed_new_tunnel_is_cleaned(self):
        for success in (True, False):
            with self.subTest(success=success), \
                 patch.object(vpn, 'ready', return_value=False), \
                 patch.object(vpn, 'managed_pid', return_value=123), \
                 patch.object(vpn, 'wait_ready', side_effect=[False, success]), \
                 patch.object(vpn, 'down') as down, \
                 patch.object(vpn, 'run', return_value=subprocess.CompletedProcess([], 0)), \
                 patch.object(vpn, 'lookup', return_value=None), \
                 patch.object(vpn, 'lookup_totp', return_value=None), \
                 patch.object(vpn, 'authenticate', return_value=subprocess.CompletedProcess([], 0, stdout='cookie')) as auth:
                if success:
                    vpn.up()
                else:
                    with self.assertRaisesRegex(core.Error, 'DNS did not become available'):
                        vpn.up()
                self.assertEqual(down.call_count, 1 if success else 2)
                auth.assert_called_once()

    def test_failed_stop_prevents_new_login(self):
        with patch.object(vpn, 'ready', return_value=False), \
             patch.object(vpn, 'managed_pid', return_value=123), \
             patch.object(vpn, 'wait_ready', return_value=False), \
             patch.object(vpn, 'down', side_effect=core.Error('Could not stop the VPN')), \
             patch.object(vpn, 'authenticate') as auth:
            with self.assertRaisesRegex(core.Error, 'Could not stop'):
                vpn.up()
            auth.assert_not_called()

    def test_bars_show_free_share_and_unknown_separately(self):
        self.assertEqual(str(availability_bar(4, 4)), '████████ 4(4)')
        self.assertEqual(str(availability_bar(1, 4)), '██────── 1(4)')
        self.assertEqual(str(availability_bar(0, 4)), '──────── 0(4)')
        self.assertEqual(str(availability_bar(None, 4)), '???????? ?(4)')


class DashboardTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.directory = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.stack.enter_context(patch.object(core, 'CONFIG', Path(self.directory)/'config'))
        self.stack.enter_context(patch.object(core, 'STATE', Path(self.directory)/'state'))
        self.addCleanup(self.stack.close)

    async def test_startup_loads_realistic_inventory_without_connect_key(self):
        nodes = core.parse_nodes('NodeName=hendrixgpu01 State=IDLE Partitions=gpu Gres=gpu:h100:4 GresUsed=gpu:h100:0')
        app = HendrixApp()
        app.startup_connected = True
        with patch.object(app.backend, 'nodes', return_value=nodes) as query, \
             patch.object(app.backend, 'jobs', return_value=[]), \
             patch.object(app.backend, 'cluster_queue', return_value=([], '')):
            async with app.run_test(size=(90, 40)) as pilot:
                await pilot.pause(.3)
                self.assertTrue(app.connected)
                query.assert_called_once()
                self.assertEqual(app.query_one('#models', DataTable).row_count, 1)
                self.assertEqual(str(app.query_one('#models', DataTable).get_cell('h100', 'gpu')), '████████ 4(4)')
                self.assertEqual(app.focused.id, 'models')

    async def test_failed_startup_leaves_retry_visible_and_no_background_login(self):
        app = HendrixApp()
        app.startup_error = 'VPN unavailable'
        with patch.object(app.backend, 'remote', side_effect=AssertionError('Unexpected query')):
            async with app.run_test(size=(80, 30)) as pilot:
                await pilot.pause()
                self.assertFalse(app.connected)
                self.assertIn('c retry', str(app.query_one('#connection', Static).render()))
                self.assertEqual(app.connection_detail, 'VPN unavailable')

    async def test_columns_all_compact_optional_toggle_save_reload_and_cancel(self):
        app = HendrixApp()
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.press('C')
            await pilot.pause()
            self.assertIsInstance(app.screen, ColumnChooser)
            chooser = app.screen
            await pilot.click('#column-all')
            await pilot.click('#column-save')
            await pilot.pause()
            self.assertEqual(len(app.query_one('#models', DataTable).columns), 7)
            self.assertEqual(load_columns()['models'], {key for key, _, _ in TABLE_COLUMNS['models']})
            await pilot.press('C')
            await pilot.pause()
            chooser = app.screen
            chooser.query_one('#column-table', Select).value = 'nodes'
            await pilot.pause()
            chooser.query_one('#column-list', SelectionList).select('cpu')
            chooser.query_one('#column-table', Select).value = 'jobs'
            await pilot.pause()
            await pilot.click('#column-all')
            chooser.query_one('#column-table', Select).value = 'cluster-queue'
            await pilot.pause()
            await pilot.click('#column-all')
            await pilot.click('#column-save')
            await pilot.pause()
            self.assertIn('cpu', load_columns()['nodes'])
            self.assertEqual(len(app.query_one('#jobs', DataTable).columns), 9)
            self.assertEqual(len(app.query_one('#cluster-queue', DataTable).columns), 10)
            saved = (core.CONFIG / 'ui.json').read_text()
            await pilot.press('C')
            await pilot.pause()
            await pilot.click('#column-compact')
            await pilot.press('escape')
            self.assertEqual((core.CONFIG / 'ui.json').read_text(), saved)
            await pilot.press('C')
            await pilot.pause()
            await pilot.resize_terminal(60, 24)
            await pilot.pause()
            await pilot.click('#column-compact')
            await pilot.click('#column-save')
            await pilot.pause()
            self.assertEqual(load_columns()['models'], COMPACT_COLUMNS['models'])

    def test_corrupt_preferences_fall_back_and_identity_columns_cannot_disappear(self):
        core.CONFIG.mkdir()
        path = core.CONFIG / 'ui.json'
        for contents in ('{', 'null', '[]'):
            path.write_text(contents)
            self.assertEqual(load_columns(), COMPACT_COLUMNS)
        path.write_text(json.dumps({'models': ['cpu', 'obsolete', {}], 'nodes': []}))
        choices = load_columns()
        self.assertEqual(choices['models'], {'model', 'gpu', 'cpu'})
        self.assertEqual(choices['nodes'], {'node', 'model', 'gpu'})
