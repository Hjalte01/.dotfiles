"""Log following across Slurm job completion, without connecting to a cluster."""
import unittest
from unittest.mock import patch

from hendrix import core


class LogPathTests(unittest.TestCase):
    def setUp(self):
        self.backend = core.Backend(core.Profile('Test', '/tmp/local', '~/remote'))

    def test_follow_retains_live_paths_after_job_leaves_scheduler(self):
        with patch.object(self.backend, 'matching_record', return_value=None), \
                patch.object(self.backend, 'remote', side_effect=[
                    'JobId=628 StdOut=/runs/slurm-628_3.out StdErr=/runs/slurm-628_3.err',
                    'training step 60001', 'training step 60002']) as remote:
            self.assertEqual(self.backend.logs('628_3'), 'training step 60001')
            self.assertEqual(self.backend.logs('628_3'), 'training step 60002')
        self.assertEqual(sum('scontrol' in call.args[0] for call in remote.call_args_list), 1)

    def test_completed_external_job_finds_saved_stdout_and_stderr(self):
        for stderr, suffix in ((False, 'out'), (True, 'err')):
            with self.subTest(stderr=stderr):
                path = f'/project/results/runs/table-b-first/slurm-9443_3.{suffix}'
                with patch.object(self.backend, 'matching_record', return_value=None), \
                        patch.object(self.backend, 'remote_root', return_value='/project'), \
                        patch.object(self.backend, 'remote', side_effect=[
                            core.Error('slurm_load_jobs error: Invalid job id specified'),
                            path + '\n']) as remote:
                    self.assertEqual(self.backend.log_path('9443_3', stderr), path)
                    self.assertEqual(self.backend.log_path('9443_3', stderr), path)
                self.assertEqual(remote.call_count, 2)
                search = remote.call_args_list[1].args[0]
                self.assertIn('-maxdepth 2', search)
                self.assertIn(f'*-9443_3.{suffix}', search)

    def test_pending_array_parent_path_resolves_selected_task(self):
        for reported in ('/runs/slurm-628_4294967294.out', '/runs/slurm-%A_%a.out'):
            with self.subTest(reported=reported):
                backend = core.Backend(core.Profile('Test', '/tmp/local', '~/remote'))
                with patch.object(backend, 'matching_record', return_value=None), \
                        patch.object(backend, 'remote', return_value=f'StdOut={reported}'):
                    self.assertEqual(backend.log_path('628_3'), '/runs/slurm-628_3.out')

    def test_connection_errors_are_not_misreported_as_missing_logs(self):
        with patch.object(self.backend, 'matching_record', return_value=None), \
                patch.object(self.backend, 'remote', side_effect=core.Error('SSH timed out')) as remote:
            with self.assertRaisesRegex(core.Error, 'SSH timed out'):
                self.backend.log_path('628_3')
        self.assertEqual(remote.call_count, 1)

    def test_ambiguous_saved_logs_do_not_follow_the_wrong_run(self):
        with patch.object(self.backend, 'matching_record', return_value=None), \
                patch.object(self.backend, 'remote_root', return_value='/project'), \
                patch.object(self.backend, 'remote', side_effect=[
                    core.Error('Invalid job id specified'),
                    '/project/results/runs/a/slurm-628_3.out\n'
                    '/project/results/runs/b/slurm-628_3.out\n']):
            with self.assertRaisesRegex(core.Error, 'No unique saved log'):
                self.backend.log_path('628_3')


if __name__ == '__main__':
    unittest.main()
