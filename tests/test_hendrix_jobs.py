"""Offline coverage for job views and naming; never submits real cluster jobs."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hendrix import core
from hendrix.app import HendrixApp
from textual.widgets import Button, DataTable, Input, Select


def job(ident, state, end=None):
    return dict(id=str(ident), state=state, end=end, name='old-slurm-name',
                elapsed='00:01:00', limit='01:00:00', reason='node',
                gpu='billing=7,cpu=4,gres/gpu:l40s=1,gres/gpu=1,mem=32G')


class JobViewTests(unittest.TestCase):
    def test_array_tasks_have_same_identity_in_queue_and_accounting(self):
        backend = core.Backend(core.Profile('Test', '/tmp/local', '~/remote'))
        queue = '\n'.join(f'9443_{i}|meanflow|RUNNING|5:19|2-00:00:00|node|gpu:l40s:1|gpu'
                          for i in range(4))
        accounting = '\n'.join(f'9443_{i}|meanflow|RUNNING|00:05:19|2-00:00:00|node|gres/gpu=1|0:0|Unknown'
                               for i in range(4))
        def remote(command):
            self.assertIn('squeue -r -h', command)
            self.assertIn('"%i|%j|%T|%M|%l|%R|%b|%P"', command)
            if 'sacct' in command:
                self.assertIn('--starttime now-7days', command)
            return queue + ('\n__HENDRIX_HISTORY__\n' + accounting if 'sacct' in command else '')
        with patch.object(backend, 'remote', side_effect=remote):
            history = backend.jobs(history=True)
            refreshed = backend.jobs(history=False)
        expected = {f'9443_{i}' for i in range(4)}
        self.assertEqual({j['id'] for j in history}, expected)
        self.assertEqual({j['id'] for j in refreshed}, expected)
        self.assertEqual(len(history), 4)
        self.assertEqual(len(core.visible_jobs(history, 'active')), 4)

    def test_active_and_recent_finished_do_not_hide_transitional_states(self):
        jobs = [job(1, 'RUNNING'), job(2, 'PENDING'), job(3, 'CONFIGURING'),
                job(4, 'COMPLETING'), job(5, 'SUSPENDED'), job(6, 'FUTURE_STATE'),
                job(20, 'FAILED'), job(21, 'CANCELLED by 123'), job(22, 'COMPLETED'),
                job(23, 'OUT_OF_MEMORY'), job(24, 'TIMEOUT')]
        self.assertEqual(len(core.visible_jobs(jobs, 'active')), 6)
        rows = core.visible_jobs(jobs)
        self.assertEqual([j['id'] for j in rows[-3:]], ['24', '23', '22'])
        self.assertEqual(len(rows), 9)
        self.assertEqual(len(core.visible_jobs(jobs, 'all')), 11)
        self.assertEqual(len(core.visible_jobs(jobs, 'finished', 0)), 0)
        self.assertEqual(len(core.visible_jobs(jobs, 'finished', -1)), 5)
        self.assertEqual(len(core.visible_jobs(jobs, 'recent', 0)), 6)
        with self.assertRaises(core.Error):
            core.visible_jobs(jobs, 'recent', -2)
        self.assertEqual([j['id'] for j in core.visible_jobs(jobs, 'completed')], ['22'])

    def test_recent_means_completion_time_not_submission_id(self):
        jobs = [job(1, 'COMPLETED', '2026-10-05T15:00:00'),
                job(20, 'COMPLETED', '2026-10-05T14:00:00')]
        self.assertEqual(core.visible_jobs(jobs, 'finished', 1)[0]['id'], '1')

    def test_pending_array_ranges_remain_visible(self):
        rows = core.visible_jobs([job('10_[1-5%2]', 'PENDING'), job('11_0', 'RUNNING')], 'active')
        self.assertEqual([j['id'] for j in rows], ['11_0', '10_[1-5%2]'])

    def test_gpu_resources_compacted(self):
        self.assertEqual(core.compact_job_gpu(job(1, 'COMPLETED')['gpu']), 'gpu:l40s:1')
        self.assertEqual(core.compact_job_gpu('cpu=4,gres/gpu=2,mem=32G'), 'gpu:any:2')
        self.assertEqual(core.compact_job_gpu('gpu:l40s:1'), 'gpu:l40s:1')

    def test_names_and_validation(self):
        profile = core.Profile('MeanFlow-Thesis', '/tmp/local', '~/remote')
        name = core.default_run_name(profile, {'name': 'MNIST iMF'}, dt.datetime(2026, 10, 5, 19, 30))
        self.assertEqual(name, 'meanflow-thesis--mnist-imf--20261005-193000')
        core.validate_run_name(name)
        for invalid in ['', '--flag', 'name with spaces', '$(command)', 'x' * 97]:
            with self.assertRaises(core.Error):
                core.validate_run_name(invalid)


class JobUI(unittest.IsolatedAsyncioTestCase):
    async def test_visible_rows_resize_columns_and_clamp_horizontal_scroll(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(core, 'CONFIG', Path(directory)/'config'), \
             patch.object(core, 'STATE', Path(directory)/'state'):
            app = HendrixApp()
            async with app.run_test(size=(70, 35)) as pilot:
                app.jobs = [job(1, 'RUNNING'), job(2, 'FAILED'), job(3, 'COMPLETED'),
                            job(4, 'CANCELLED'), job(5, 'TIMEOUT')]
                app.jobs[-1]['name'] = 'a much longer finished run name than the active run'
                app.render_jobs()
                await pilot.pause()
                table = app.query_one('#jobs', DataTable)
                full_widths = [column.get_render_width(table) for column in table.columns.values()]
                table.scroll_to(x=80, animate=False)
                await pilot.pause()
                for value, count in [('0', 1), ('3', 4), ('-1', 5), ('0', 1)]:
                    horizontal = table.scroll_x
                    app.query_one('#jobs-limit', Input).value = value
                    await pilot.pause()
                    self.assertEqual(table.row_count, count)
                    widths = [column.get_render_width(table) for column in table.columns.values()]
                    if value == '0':
                        self.assertLess(widths[1], full_widths[1])
                        self.assertLess(sum(widths), sum(full_widths))
                    else:
                        self.assertEqual(widths, full_widths)
                    self.assertEqual(table.scroll_x, min(horizontal, table.max_scroll_x))
                # Refreshing the same rows must not accumulate stale widths.
                compact = [column.get_render_width(table) for column in table.columns.values()]
                app.render_jobs()
                await pilot.pause()
                self.assertEqual([column.get_render_width(table) for column in table.columns.values()], compact)
                app.query_one('#jobs-limit', Input).value = '-1'
                await pilot.pause()
                app.jobs.pop()
                app.render_jobs()
                await pilot.pause()
                self.assertLess(list(table.columns.values())[1].get_render_width(table), full_widths[1])

    async def test_follow_off_allows_switching_logs_by_job_selection(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(core, 'CONFIG', Path(directory)/'config'), \
             patch.object(core, 'STATE', Path(directory)/'state'):
            app = HendrixApp()
            with patch.object(app.backend, 'logs', side_effect=lambda ident, stderr=False: f'log for {ident}'):
                async with app.run_test(size=(110, 35)) as pilot:
                    app.jobs = [job(1, 'RUNNING'), job(2, 'RUNNING')]
                    app.render_jobs()
                    await pilot.pause()
                    app.action_follow()
                    await pilot.pause()
                    self.assertTrue(app.log_follow)
                    self.assertEqual(app.log_job, '2')
                    app.action_follow()
                    self.assertFalse(app.log_follow)
                    self.assertEqual(str(app.query_one('#follow', Button).label), 'Follow: off')
                    app.query_one('#jobs', DataTable).move_cursor(row=1)
                    await pilot.pause()
                    self.assertEqual(app.log_job, '1')
                    self.assertEqual(app.log_text, 'log for 1')
                    self.assertFalse(app.log_follow)
                    app.action_follow()
                    await pilot.pause()
                    app.query_one('#jobs', DataTable).move_cursor(row=0)
                    await pilot.pause()
                    self.assertEqual(app.log_job, '2')
                    self.assertEqual(app.log_text, 'log for 2')
                    self.assertTrue(app.log_follow)

    async def test_filter_controls_and_legacy_preset_names(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(core, 'CONFIG', Path(directory)/'config'), \
             patch.object(core, 'STATE', Path(directory)/'state'):
            app = HendrixApp()
            record = dict(host=app.profile.host, project=app.profile.name, job_id='3',
                          script=app.profile.presets[0]['script'], args=app.profile.presets[0]['args'])
            with patch.object(app.backend, 'history', return_value=[record]):
                async with app.run_test(size=(110, 35)) as pilot:
                    app.jobs = [job(1, 'FAILED'), job(2, 'COMPLETED'), job(3, 'RUNNING'),
                                job(4, 'COMPLETED'), job(5, 'COMPLETED')]
                    app.render_jobs()
                    table = app.query_one('#jobs', DataTable)
                    self.assertEqual(table.row_count, 4)
                    self.assertEqual(table.get_cell('3', 'run'), app.profile.presets[0]['name'])
                    app.query_one('#jobs-view', Select).value = 'active'
                    await pilot.pause()
                    self.assertEqual(table.row_count, 1)
                    app.query_one('#jobs-view', Select).value = 'recent'
                    app.query_one('#jobs-limit', Input).value = '1'
                    await pilot.pause()
                    self.assertEqual(table.row_count, 2)
                    app.query_one('#jobs-view', Select).value = 'all'
                    await pilot.pause()
                    self.assertEqual(table.row_count, 5)
                    await pilot.resize_terminal(60, 24)
                    await pilot.pause()
