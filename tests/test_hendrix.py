"""Offline tests: no SSH, VPN authentication, or Slurm allocation is performed."""
import asyncio
from contextlib import ExitStack
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from hendrix import core, vpn
from hendrix.app import Confirm, CopyRequest, Help, HendrixApp, SubmitForm
from textual.widgets import Button, DataTable, Input, Select, TabbedContent

NODES = '''NodeName=hendrixgpu01fl CPUTot=96 RealMemory=708000 Gres=gpu:a100:6(S:0-1) State=MIXED Partitions=gpu,preempt AllocTRES=cpu=4,gres/gpu=2,gres/gpu:a100=2 GresUsed=gpu:a100:2(IDX:0-1)
NodeName=hendrixgpu16fl CPUTot=128 CPUEfctv=124 CPUAlloc=0 RealMemory=2000000 AllocMem=0 Gres=gpu:h100:4 State=IDLE Partitions=gpu AllocTRES=gres/gpu=0 GresUsed=gpu:h100:0(IDX:N/A)
NodeName=hendrixgpu18fl CPUTot=48 RealMemory=110000 Gres=gpu:titanx:2,gpu:titan:1 State=MIXED Partitions=gpu AllocTRES=gres/gpu=1 GresUsed=gpu:titanx:1(IDX:1),gpu:titan:0(IDX:N/A)
NodeName=down CPUTot=4 RealMemory=100 Gres=gpu:a100:3 State=IDLE+DRAIN Partitions=gpu AllocTRES=gres/gpu=0 Reason=Maintenance window [admin]
NodeName=unknown CPUTot=4 RealMemory=100 Gres=gpu:a100:2 State=MIXED Partitions=gpu AllocTRES=cpu=4
'''


class LocalBackend(core.Backend):
    """Execute the remote shell against disposable directories, with a fake sbatch."""
    lose_response = False

    def remote(self, command, timeout=20):
        if self.lose_response and 'sbatch --parsable' in command:
            raise core.Error('Simulated connection loss after job acceptance')
        result = subprocess.run(['bash', '-c', command], capture_output=True, text=True, timeout=timeout)
        if result.returncode:
            raise core.Error(result.stderr)
        return result.stdout


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(core, 'CONFIG', self.root / 'config'))
        self.stack.enter_context(patch.object(core, 'STATE', self.root / 'state'))
        self.stack.enter_context(patch.object(Path, 'home', return_value=self.root))
        self.source = self.root / 'local project'
        self.source.mkdir()
        self.remote = self.root / "remote project 'quote'"
        self.profile = core.Profile('Test', str(self.source), str(self.remote), presets=[
            dict(name='smoke', script='scripts/hendrix/smoke.sbatch', args=[], time='00:30:00')])
        batch = self.source / 'scripts/hendrix'
        batch.mkdir(parents=True)
        (batch / 'smoke.sbatch').write_text('#!/bin/sh\ntrue\n')
        (self.source / 'model.py').write_text('version = 1\n')
        bindir = self.root / 'bin'
        bindir.mkdir()
        sbatch = bindir / 'sbatch'
        sbatch.write_text('#!/bin/sh\nprintf "12345\\n"\n')
        sbatch.chmod(0o755)
        self.stack.enter_context(patch.dict(os.environ, {'PATH': str(bindir) + ':' + os.environ['PATH']}))
        self.backend = LocalBackend(self.profile)
        # Replace only rsync's SSH destination with a local path.
        self.real_run = subprocess.run
        def fake_run(args, **kwargs):
            if isinstance(args, list) and args and args[0] == 'rsync' and args[-1].startswith('hendrix:'):
                args = args.copy()
                at = args.index('-e')
                del args[at:at + 2]
                args[-1] = args[-1].removeprefix('hendrix:')
            return self.real_run(args, **kwargs)
        self.stack.enter_context(patch.object(core.subprocess, 'run', side_effect=fake_run))

    def tearDown(self):
        self.stack.close()
        self.temp.cleanup()

    def test_inventory_deduplication_unknown_and_mixed_models(self):
        nodes = core.parse_nodes(NODES + NODES.splitlines()[0] + '\n')
        self.assertEqual(len(nodes), 5)
        summary = {r['model']: r for r in core.summarize(nodes)}
        self.assertEqual(summary['a100']['total'], 11)
        self.assertTrue(summary['a100']['unknown'])
        self.assertEqual(summary['a100']['usable'], 4)  # Drained node is excluded.
        self.assertEqual(summary['h100']['unallocated'], 4)
        titan = next(n for n in nodes if n['name'] == 'hendrixgpu18fl')
        self.assertEqual(titan['used'], {'titanx': 1, 'titan': 0})
        unknown = core.parse_nodes('NodeName=x Gres=gpu:a:2,gpu:b:2 State=MIXED AllocTRES=gres/gpu=1')[0]
        self.assertEqual(unknown['used'], {'a': None, 'b': None})

    def test_profiles_and_validation(self):
        core.save_profiles([self.profile])
        self.assertEqual(core.load_profiles()[0], self.profile)
        for bad in ['../secret', '/data', '.hendrix/source']:
            with self.assertRaises(core.Error):
                core.relative_path(bad)
        with self.assertRaises(core.Error):
            core.Profile('Bad', str(self.source), '/', host='-oProxyCommand=x').validate()

    def test_remaining_resources_and_request_semantics(self):
        nodes = core.parse_nodes('''NodeName=a CPUTot=96 CPUEfctv=92 CPUAlloc=12 RealMemory=65536 AllocMem=8192 Gres=gpu:a100:2 State=MIXED AllocTRES=cpu=99,mem=64G,gres/gpu=1 Reason=(null)
NodeName=b CPUTot=32 RealMemory=65536 Gres=gpu:h100:1 State=MIXED AllocTRES=cpu=4,mem=16G,gres/gpu=0
NodeName=c CPUTot=16 RealMemory=32768 Gres=gpu:a100:2,gpu:a40:2 State=MIXED AllocTRES=cpu=20,mem=64G,gres/gpu=0
NodeName=d CPUTot=8 RealMemory=1024 Gres=gpu:a100:1 State=MIXED
''')
        self.assertEqual((nodes[0]['cpu_free'], nodes[0]['ram_free']), (80, 57344))
        self.assertEqual(nodes[0]['reason'], '')
        self.assertEqual((nodes[1]['cpu_free'], nodes[1]['ram_free']), (28, 49152))
        self.assertEqual((nodes[2]['cpu_free'], nodes[2]['ram_free']), (0, 0))
        self.assertIsNone(nodes[3]['cpu_free'])
        self.assertIsNone(nodes[3]['ram_free'])
        self.assertEqual(core.free_total(4, 6), '4(6)')
        self.assertEqual(core.free_total(None, 8), '?(8)')
        self.assertEqual(core.free_total(49152, 65536, gib=True), '48(64)')
        summary = {r['model']: r for r in core.summarize(nodes[:3])}
        self.assertEqual(summary['a100']['cpu_total'], 108)
        self.assertEqual(summary['a40']['cpu_total'], 16)
        groups = core.request_groups(nodes, [('a', 'a100'), ('c', 'a100'), ('b', 'h100')])
        self.assertEqual(groups, {'h100': ['b'], 'a100': ['a', 'c']})
        self.assertEqual(core.gpu_request('a100'), '#SBATCH --gres=gpu:a100:1\n')
        self.assertEqual(core.gpu_request('untyped'), '#SBATCH --gres=gpu:1\n')
        pinned = core.gpu_request('h100', 'hendrixgpu16fl')
        self.assertIn('--nodes=1\n#SBATCH --nodelist=hendrixgpu16fl', pinned)
        for model in ['a100,h100', 'a100:2', 'a100\n#SBATCH --nodes=20']:
            with self.assertRaises(core.Error):
                core.gpu_request(model)

    def test_editor_can_repair_invalid_profiles(self):
        from hendrix import cli
        path = core.CONFIG / 'profiles.json'
        path.parent.mkdir(parents=True)
        path.write_text('broken json')
        def repair(*args, **kwargs):
            core.save_profiles([self.profile])
            return subprocess.CompletedProcess([], 0)
        with patch.object(cli, 'CONFIG', core.CONFIG), patch.object(cli.subprocess, 'run', side_effect=repair):
            cli.edit_profiles()
        self.assertEqual(core.load_profiles()[0].name, 'Test')

    def test_preview_does_not_mutate_remote(self):
        output = self.backend.sync(dry=True)
        self.assertIn('model.py', output)
        self.assertFalse(self.remote.exists())
        self.assertEqual(self.backend.history(), [])

    def test_snapshot_survives_sync_shared_data_and_deletion(self):
        for shared in ['data', 'results/runs', '.venv-hendrix']:
            folder = self.remote / shared
            folder.mkdir(parents=True)
            (folder / 'keep').write_text('keep')
            local = self.source / shared
            local.mkdir(parents=True)
            (local / 'do-not-upload').write_text('local')
        (self.source / 'obsolete.py').write_text('old')
        resources = dict(partition='gpu', model='a100', gpus=1, cpus=4, memory='32G', time='00:30:00')
        manifest = self.backend.submit(self.profile.presets[0], resources)
        snapshot = Path(manifest['snapshot'])
        self.assertEqual(manifest['job_id'], '12345')
        self.assertEqual((snapshot / 'model.py').read_text(), 'version = 1\n')
        self.assertTrue((snapshot / '.venv-hendrix').is_symlink())
        self.assertEqual((snapshot / 'data/keep').read_text(), 'keep')
        self.assertFalse((snapshot / 'data/do-not-upload').exists())
        (self.source / 'model.py').write_text('version = 2\n')
        (self.source / 'obsolete.py').unlink()
        self.backend.sync()
        self.assertEqual((snapshot / 'model.py').read_text(), 'version = 1\n')
        self.assertTrue((snapshot / 'obsolete.py').exists())
        self.assertFalse((self.remote / '.hendrix/source/obsolete.py').exists())
        self.assertEqual((self.remote / 'data/keep').read_text(), 'keep')
        self.assertEqual((self.remote / 'results/runs/keep').read_text(), 'keep')

    def test_unmarked_mirror_and_symlink_rejected(self):
        (self.remote / '.hendrix/source').mkdir(parents=True)
        with self.assertRaises(core.Error):
            self.backend.sync()
        (self.remote / '.hendrix/source').rmdir()
        (self.remote / '.hendrix/source').symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(core.Error):
            self.backend.sync()
        self.assertEqual((self.source / 'model.py').read_text(), 'version = 1\n')

    def test_failed_sync_prevents_submission(self):
        self.backend._sync = lambda *_: (_ for _ in ()).throw(core.Error('sync failed'))
        with self.assertRaisesRegex(core.Error, 'sync failed'):
            self.backend.submit(self.profile.presets[0], dict(partition='gpu', model='h100', gpus=1,
                                cpus=4, memory='32G', time='00:30:00'))
        self.assertFalse((self.remote / '.hendrix/snapshots').exists())

    def test_uncertain_submission_is_recorded(self):
        self.backend.lose_response = True
        with self.assertRaises(core.UncertainSubmission):
            self.backend.submit(self.profile.presets[0], dict(partition='gpu', model='h100', gpus=1,
                                cpus=4, memory='32G', time='00:30:00'))
        self.assertEqual(self.backend.history()[-1]['status'], 'uncertain')
        with self.assertRaisesRegex(core.UncertainSubmission, 'Resolve the previous'):
            self.backend.submit(self.profile.presets[0], dict(partition='gpu', model='h100', gpus=1,
                                cpus=4, memory='32G', time='00:30:00'))
        record = self.backend.unresolved()[0][1]
        with patch.object(self.backend, 'remote', return_value=f'12345|hendrix-{record["token"]}\n'):
            self.assertIn('Recovered accepted job', self.backend.reconcile())
        self.assertEqual(self.backend.unresolved(), [])
        self.assertEqual(self.backend.history()[-1]['job_id'], '12345')

    def test_two_processes_cannot_sync_same_project(self):
        with core.project_lock(self.profile):
            with self.assertRaisesRegex(core.Error, 'Another sync'):
                self.backend.sync()

    def test_state_filter_and_gpu_preference(self):
        nodes = core.parse_nodes(NODES)
        visible = core.visible_gpu_nodes(nodes)
        self.assertEqual({n['name'] for n in visible}, {'hendrixgpu01fl', 'hendrixgpu16fl', 'hendrixgpu18fl'})
        rows = sorted(((n, model) for n in visible for model in n['capacity']),
                      key=lambda pair: core.gpu_row_order(*pair))
        self.assertEqual(rows[0][1], 'h100')
        summary = {r['model']: r for r in core.summarize(visible)}
        self.assertEqual(summary['a100']['total'], 6)  # Excludes drained and unknown-free nodes.
        self.assertEqual(len(core.visible_gpu_nodes(nodes, 'all')), 5)
        self.assertEqual([n['name'] for n in core.visible_gpu_nodes(nodes, 'unavailable')], ['down'])
        self.assertEqual(len(core.visible_gpu_nodes(nodes, 'MIXED')), 3)
        powered = core.parse_nodes('NodeName=x Gres=gpu:h100:4 State=IDLE+POWERED_DOWN AllocTRES=gres/gpu=0')
        self.assertFalse(powered[0]['eligible'])
        self.assertEqual(core.visible_gpu_nodes(powered), [])

    def test_slurm_job_parsing(self):
        q = core.parse_queue('123|run|PENDING|0:00|5:00:00|Resources|gpu:a100:1|gpu\n')
        self.assertEqual(q[0]['reason'], 'Resources')
        a = core.parse_accounting('123|run|COMPLETED|00:01:00|05:00:00|node|gres/gpu=1|0:0|\n')
        self.assertEqual(a[0]['exit'], '0:0')


class LoginTests(unittest.TestCase):
    def test_vpn_waits_for_dns_without_reauthenticating(self):
        with patch.object(vpn, 'run', return_value=subprocess.CompletedProcess([], 0)), \
             patch.object(vpn, 'ready', side_effect=[False, False, False, True]), \
             patch.object(vpn, 'managed_pid', side_effect=[None, 123]), \
             patch.object(vpn, 'disable_dns'), patch.object(vpn, 'lookup', return_value=None), \
             patch.object(vpn.time, 'sleep'), \
             patch.object(vpn, 'authenticate', return_value=subprocess.CompletedProcess([], 0, stdout='cookie')) as auth, \
             patch.object(vpn, 'down') as down:
            vpn.up()
            auth.assert_called_once()
            down.assert_not_called()

    def test_dns_timeout_cleans_up_connection(self):
        with patch.object(vpn, 'run', return_value=subprocess.CompletedProcess([], 0)), \
             patch.object(vpn, 'ready', return_value=False), \
             patch.object(vpn, 'managed_pid', return_value=None), \
             patch.object(vpn, 'disable_dns'), patch.object(vpn, 'lookup', return_value=None), \
             patch.object(vpn, 'authenticate', return_value=subprocess.CompletedProcess([], 0, stdout='cookie')), \
             patch.object(vpn, 'wait_ready', return_value=False), \
             patch.object(vpn, 'down') as down:
            with self.assertRaisesRegex(core.Error, 'within 20 seconds'):
                vpn.up()
            down.assert_called_once()

    def test_dns_wait_is_bounded(self):
        with patch.object(vpn, 'ready', return_value=False) as ready, \
             patch.object(vpn, 'managed_pid', return_value=123), \
             patch.object(vpn.time, 'monotonic', side_effect=[0, 0, 1, 20]), \
             patch.object(vpn.time, 'sleep'):
            self.assertFalse(vpn.wait_ready())
            ready.assert_called_once_with(timeout=3)

    def test_dns_wait_stops_when_tunnel_exits(self):
        with patch.object(vpn, 'ready', return_value=False), \
             patch.object(vpn, 'managed_pid', return_value=None), \
             patch.object(vpn.time, 'sleep') as sleep:
            self.assertFalse(vpn.wait_ready())
            sleep.assert_not_called()

    def test_disconnect_cleans_dns_before_restoring_tailscale(self):
        events = []
        def run(args, **kwargs):
            events.append(args)
            return subprocess.CompletedProcess(args, 0)
        with patch.object(vpn, 'managed_pid', return_value=123), \
             patch.object(Path, 'exists', return_value=False), \
             patch.object(vpn, 'run', side_effect=run), \
             patch.object(vpn, 'restore_dns', side_effect=lambda: events.append('restore')):
            vpn.down()
        self.assertEqual(events, [['sudo', 'kill', '-INT', '123'],
                                  ['sudo', 'resolvconf', '-d', 'hendrix0'], 'restore'])

    def test_disconnect_preserves_dns_if_tunnel_is_still_running(self):
        with patch.object(vpn, 'managed_pid', return_value=123), \
             patch.object(Path, 'exists', return_value=True), \
             patch.object(vpn.time, 'sleep'), \
             patch.object(vpn, 'run', return_value=subprocess.CompletedProcess([], 0)) as run, \
             patch.object(vpn, 'restore_dns') as restore:
            with self.assertRaisesRegex(core.Error, 'has not stopped'):
                vpn.down()
            self.assertEqual(run.call_count, 1)
            restore.assert_not_called()

    def test_failed_authentication_is_not_retried(self):
        with patch.object(vpn, 'run', return_value=subprocess.CompletedProcess([], 0)), \
             patch.object(vpn, 'ready', return_value=False), patch.object(vpn, 'managed_pid', return_value=None), \
             patch.object(vpn, 'disable_dns'), patch.object(vpn, 'restore_dns') as restore, \
             patch.object(vpn, 'lookup', return_value='very-secret'), \
             patch.object(vpn, 'authenticate', return_value=subprocess.CompletedProcess([], 1, stdout='')) as auth:
            with self.assertRaises(core.Error):
                vpn.up()
            auth.assert_called_once()
            self.assertNotIn('very-secret', ' '.join(auth.call_args.args[0]))
            restore.assert_called_once()

    def test_saved_password_then_interactive_totp_on_tty(self):
        import pty
        import hashlib
        import sys
        import termios
        import threading
        master, slave = pty.openpty()
        original = termios.tcgetattr(slave)
        # Simulate OpenConnect: password from stdin, then a later terminal-only MFA read.
        program = ('import sys,os,termios,hashlib; '
                   'assert os.isatty(0); '
                   'password=sys.stdin.readline().strip(); '
                   'termios.tcgetattr(0); '
                   'code=sys.stdin.readline().strip(); '
                   f'assert hashlib.sha256(password.encode()).hexdigest() == "{hashlib.sha256(b"very-secret").hexdigest()}"; '
                   'assert code == "123456"; '
                   'print("cookie-only")')
        timer = threading.Timer(.2, lambda: os.write(master, b'123456\n'))
        timer.start()
        try:
            result = vpn.authenticate([sys.executable, '-c', program], 'very-secret', os.ttyname(slave))
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), 'cookie-only')
            self.assertNotIn('very-secret', ' '.join(result.args))
            self.assertEqual(termios.tcgetattr(slave), original)
        finally:
            timer.join()
            os.close(master)
            os.close(slave)

    def test_interactive_login_preserves_stdin(self):
        with patch.object(vpn, 'run', return_value=subprocess.CompletedProcess([], 0, stdout='cookie')) as run:
            vpn.authenticate(['openconnect', '--cookieonly', 'vpn.ku.dk'], None)
            self.assertNotIn('input', run.call_args.kwargs)
            self.assertNotIn('stdin', run.call_args.kwargs)

    def test_dns_restores_previous_false(self):
        with tempfile.TemporaryDirectory() as d, patch.object(vpn, 'DNS_STATE', Path(d)/'vpn.json'):
            core.atomic_json(vpn.DNS_STATE, {'accept_dns': False})
            with patch.object(vpn, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
                vpn.restore_dns()
                self.assertIn('--accept-dns=false', run.call_args.args[0])
                self.assertFalse(vpn.DNS_STATE.exists())


class TUITests(unittest.IsolatedAsyncioTestCase):
    async def test_mount_refresh_filter_and_submission_cancel(self):
        with tempfile.TemporaryDirectory() as d, patch.object(core, 'CONFIG', Path(d)/'config'), \
             patch.object(core, 'STATE', Path(d)/'state'), patch.object(Path, 'home', return_value=Path(d)):
            with patch.object(core.Backend, 'remote', side_effect=AssertionError('Unexpected network call')):
                app = HendrixApp()
                async with app.run_test(size=(130, 50)) as pilot:
                    await pilot.pause()
                    self.assertFalse(app.connected)
                    app.nodes = core.parse_nodes(NODES)
                    app.render_nodes()
                    app.query_one('#node-filter', Input).value = 'h100'
                    await pilot.pause()
                    self.assertEqual(app.query_one('#nodes', DataTable).row_count, 1)
                    app.jobs = core.parse_queue('123|run|RUNNING|1:00|5:00:00|node|gpu:1|gpu\n')
                    app.render_jobs()
                    self.assertEqual(app.selected_job(), '123')
                    app.action_submit()
                    await pilot.pause()
                    self.assertIsInstance(app.screen, SubmitForm)
                    app.screen.query_one('#review').scroll_visible(immediate=True)
                    await pilot.pause()
                    await pilot.click('#review')
                    await pilot.pause()
                    self.assertIsInstance(app.screen, Confirm)
                    await pilot.click('#no')
                    await pilot.pause()
                    self.assertFalse(app.busy)

    async def test_hjkl_navigation_inputs_dropdowns_and_filters(self):
        with tempfile.TemporaryDirectory() as d, patch.object(core, 'CONFIG', Path(d)/'config'), \
             patch.object(core, 'STATE', Path(d)/'state'), patch.object(Path, 'home', return_value=Path(d)):
            app = HendrixApp()
            with patch.object(core.Backend, 'remote', side_effect=AssertionError('Unexpected network call')):
                async with app.run_test(size=(150, 55)) as pilot:
                    app.nodes = core.parse_nodes(NODES)
                    app.render_nodes()
                    table = app.query_one('#nodes', DataTable)
                    table.focus()
                    await pilot.press('j')
                    self.assertEqual(table.cursor_row, 1)
                    await pilot.press('k')
                    self.assertEqual(table.cursor_row, 0)
                    await pilot.press('l', 'h')  # These must not trigger job log actions.
                    self.assertIsNone(app.log_job)
                    search = app.query_one('#node-filter', Input)
                    search.focus()
                    await pilot.press('h', 'j', 'k', 'l')
                    self.assertEqual(search.value, 'hjkl')
                    search.value = ''
                    await pilot.pause()
                    state = app.query_one('#state-filter', Select)
                    state.focus()
                    await pilot.press('j', 'j', 'enter')
                    await pilot.pause()
                    self.assertEqual(state.value, 'healthy')
                    state.value = 'all'
                    await pilot.pause()
                    self.assertEqual(table.row_count, 6)
                    state.value = 'unavailable'
                    await pilot.pause()
                    self.assertEqual(table.row_count, 1)
                    self.assertEqual(str(table.get_cell(app.table_row_key(table), 'node')), 'down')
                    table.focus()
                    await pilot.press('alt+l')
                    await pilot.pause()
                    self.assertEqual(app.query_one(TabbedContent).active, 'project-tab')

    async def test_compact_layout_headers_reasons_and_help(self):
        with tempfile.TemporaryDirectory() as d, patch.object(core, 'CONFIG', Path(d)/'config'), \
             patch.object(core, 'STATE', Path(d)/'state'), patch.object(Path, 'home', return_value=Path(d)):
            app = HendrixApp()
            with patch.object(core.Backend, 'remote', side_effect=AssertionError('Unexpected network call')):
                async with app.run_test(size=(90, 60)) as pilot:
                    app.nodes = core.parse_nodes(NODES)
                    app.render_nodes()
                    await pilot.pause()
                    table = app.query_one('#nodes', DataTable)
                    models = app.query_one('#models', DataTable)
                    search = app.query_one('#node-filter', Input)
                    self.assertLess(search.region.bottom, models.region.y)
                    self.assertLess(models.region.bottom, table.region.y)
                    self.assertLessEqual(table.virtual_size.width, table.content_size.width)
                    self.assertFalse(app.query('#gpu-sort'))
                    self.assertEqual(len(models.columns), 4)
                    self.assertEqual(len(table.columns), 6)
                    self.assertEqual(next(iter(table.columns)).value, 'node')
                    self.assertEqual(str(table.get_cell(app.table_row_key(table), 'node')), 'gpu16fl')
                    self.assertEqual(str(table.get_cell(app.table_row_key(table), 'gpu')), '4(4)')
                    self.assertEqual(str(table.get_cell(app.table_row_key(table), 'cpu')), '124(124)')
                    reasons = app.query_one('#reasons', Button)
                    self.assertEqual(str(reasons.label), 'Reasons off (0)')
                    self.assertTrue(reasons.disabled)
                    app.query_one('#state-filter', Select).value = 'all'
                    await pilot.pause()
                    self.assertEqual(str(reasons.label), 'Reasons off (1)')
                    await pilot.click('#reasons')
                    await pilot.pause()
                    self.assertEqual(len(table.columns), 7)
                    self.assertIn('reason', [key.value for key in table.columns])
                    await pilot.click('#reasons')
                    await pilot.pause()
                    self.assertEqual(len(table.columns), 6)
                    # Actual mouse clicks, not direct calls to the event handler.
                    await pilot.click('#models', offset=(4, 1))
                    await pilot.pause()
                    self.assertEqual(app.sort_key, 'model')
                    self.assertFalse(app.sort_reverse)
                    self.assertEqual(str(models.get_row_at(0)[0]), 'a100')
                    await pilot.click('#models', offset=(4, 1))
                    await pilot.pause()
                    self.assertTrue(app.sort_reverse)
                    self.assertEqual(str(models.get_row_at(0)[0]), 'titanx')
                    await pilot.click('#models', offset=(17, 1))
                    await pilot.pause()
                    self.assertEqual(app.sort_key, 'gpu')
                    self.assertTrue(app.sort_reverse)
                    self.assertEqual(str(models.get_row_at(0)[0]), 'h100')
                    self.assertEqual(str(table.get_row_at(table.row_count - 1)[0]), 'unknown')
                    await pilot.click('#models', offset=(17, 1))
                    await pilot.pause()
                    self.assertFalse(app.sort_reverse)
                    self.assertEqual(str(table.get_row_at(table.row_count - 1)[0]), 'unknown')
                    table.focus()
                    await pilot.press('=')
                    self.assertEqual(app.sort_key, 'preference')
                    await pilot.resize_terminal(180, 60)
                    await pilot.pause()
                    self.assertEqual(str(table.get_cell(app.table_row_key(table), 'node')), 'hendrixgpu16fl')
                    await pilot.resize_terminal(80, 45)
                    await pilot.pause()
                    self.assertLessEqual(table.virtual_size.width, table.content_size.width)
                    self.assertGreaterEqual(search.content_size.width, 20)
                    self.assertGreaterEqual(app.query_one('#connection').region.y, 1)
                    self.assertGreaterEqual(app.query_one('#project-bar').region.y, 2)
                    # Wide memory counts fit without losing the closing parenthesis.
                    ram_column = next(c for key, c in table.columns.items() if key.value == 'ram')
                    self.assertGreaterEqual(ram_column.width, len(str(table.get_cell(app.table_row_key(table), 'ram'))))
                    await pilot.press('?')
                    await pilot.pause()
                    self.assertIsInstance(app.screen, Help)
                    self.assertLessEqual(app.screen.query_one('#help-dialog').region.right, 80)
                    await pilot.press('escape')
                    self.assertNotIsInstance(app.screen, Help)

    async def test_marks_model_copy_and_exact_node_review(self):
        import json
        with tempfile.TemporaryDirectory() as d, patch.object(core, 'CONFIG', Path(d)/'config'), \
             patch.object(core, 'STATE', Path(d)/'state'), patch.object(Path, 'home', return_value=Path(d)), \
             patch('hendrix.app.native_clipboard', return_value=True) as clipboard:
            app = HendrixApp()
            with patch.object(core.Backend, 'remote', side_effect=AssertionError('Unexpected network call')):
                async with app.run_test(size=(90, 60)) as pilot:
                    app.nodes = core.parse_nodes(NODES)
                    app.render_nodes()
                    table = app.query_one('#nodes', DataTable)
                    table.focus()
                    node_width = next(c.width for key, c in table.columns.items() if key.value == 'node')
                    await pilot.press('v', 'y')
                    await pilot.pause(.2)
                    self.assertEqual(str(table.get_cell('hendrixgpu16fl:h100', 'node')), 'gpu16fl ●')
                    self.assertEqual(next(c.width for key, c in table.columns.items() if key.value == 'node'), node_width)
                    clipboard.assert_called_with('#SBATCH --gres=gpu:h100:1\n')
                    saved = json.loads((core.STATE / 'copied-request.json').read_text())
                    self.assertEqual(saved['inspected_nodes'], ['hendrixgpu16fl'])
                    self.assertIsNone(saved['node'])
                    await pilot.press('j', 'v', 'y')
                    await pilot.pause()
                    self.assertEqual(len(app.marked_rows), 2)
                    self.assertIsInstance(app.screen, CopyRequest)
                    self.assertFalse(app.screen.query_one('#copy-node', Button).disabled)
                    await pilot.click('#copy-node')
                    await pilot.pause(.2)
                    clipboard.assert_called_with(core.gpu_request('h100', 'hendrixgpu16fl'))
                    table.focus()
                    search = app.query_one('#node-filter', Input)
                    search.value = 'a100'
                    await pilot.pause()
                    self.assertEqual(len(app.marked_rows), 2)
                    search.focus()
                    search.value = ''
                    await pilot.press('v', 'y', 'R')
                    self.assertEqual(search.value, 'vyR')
                    self.assertEqual(len(app.marked_rows), 2)
                    search.value = ''
                    await pilot.pause()
                    table.focus()
                    await pilot.press('V')
                    self.assertEqual(app.marked_rows, set())
                    self.assertEqual(str(table.get_cell('hendrixgpu16fl:h100', 'node')), 'gpu16fl')
                    # Two nodes of one model copy one GPU model request, never an OR nodelist.
                    extra = core.parse_nodes('NodeName=hendrixgpu21fl CPUTot=32 CPUAlloc=0 RealMemory=65536 AllocMem=0 Gres=gpu:a100:4 State=IDLE AllocTRES=gres/gpu=0')[0]
                    app.nodes.append(extra)
                    app.marked_rows = {('hendrixgpu01fl', 'a100'), ('hendrixgpu21fl', 'a100')}
                    app.render_nodes()
                    await pilot.press('y')
                    await pilot.pause(.2)
                    clipboard.assert_called_with('#SBATCH --gres=gpu:a100:1\n')
                    await pilot.press('Y')
                    await pilot.pause()
                    self.assertIsInstance(app.screen, CopyRequest)
                    self.assertTrue(app.screen.query_one('#copy-node', Button).disabled)
                    await pilot.press('escape')
                    app.nodes.remove(extra)
                    app.render_nodes()
                    self.assertEqual(app.marked_rows, {('hendrixgpu01fl', 'a100')})

    async def test_refresh_uses_queries_and_stops_after_failure(self):
        with tempfile.TemporaryDirectory() as d, patch.object(core, 'CONFIG', Path(d)/'config'), \
             patch.object(core, 'STATE', Path(d)/'state'), patch.object(Path, 'home', return_value=Path(d)):
            app = HendrixApp()
            def remote(command, **_):
                if command.startswith('set -e; squeue'):
                    return '123|run|PENDING|0:00|5:00:00|Resources|gpu:a100:1|gpu\n__HENDRIX_HISTORY__\n'
                if command == 'scontrol show nodes -d -o':
                    return NODES
                raise AssertionError(command)
            with patch.object(app.backend, 'remote', side_effect=remote):
                async with app.run_test(size=(130, 50)) as pilot:
                    app.action_refresh()
                    await pilot.pause(.3)
                    self.assertTrue(app.connected)
                    self.assertEqual(app.query_one('#models', DataTable).row_count, 4)
                    with patch.object(app.backend, 'remote', side_effect=core.Error('No connection')):
                        app.action_refresh()
                        await pilot.pause(.3)
                        self.assertFalse(app.connected)
                        self.assertFalse(app.log_follow)


if __name__ == '__main__':
    unittest.main()
