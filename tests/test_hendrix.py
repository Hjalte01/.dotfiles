"""Offline tests: no SSH, VPN authentication, or Slurm allocation is performed."""
import asyncio
import datetime as dt
import io
from contextlib import ExitStack
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from hendrix import core, vpn
from hendrix.app import CompareGPUs, Confirm, CopyRequest, Help, HendrixApp, SubmitForm, GPUChoices
from textual.widgets import Button, DataTable, Input, Select, TabbedContent, Collapsible

NODES = '''NodeName=hendrixgpu01fl CPUTot=96 RealMemory=708000 Gres=gpu:a100:6(S:0-1) State=MIXED Partitions=gpu,preempt AllocTRES=cpu=4,gres/gpu=2,gres/gpu:a100=2 GresUsed=gpu:a100:2(IDX:0-1)
NodeName=hendrixgpu16fl CPUTot=128 CPUEfctv=124 CPUAlloc=0 RealMemory=2000000 AllocMem=0 Gres=gpu:h100:4 State=IDLE Partitions=gpu AllocTRES=gres/gpu=0 GresUsed=gpu:h100:0(IDX:N/A)
NodeName=hendrixgpu18fl CPUTot=48 RealMemory=110000 Gres=gpu:titanx:2,gpu:titan:1 State=MIXED Partitions=gpu AllocTRES=gres/gpu=1 GresUsed=gpu:titanx:1(IDX:1),gpu:titan:0(IDX:N/A)
NodeName=down CPUTot=4 RealMemory=100 Gres=gpu:a100:3 State=IDLE+DRAIN Partitions=gpu AllocTRES=gres/gpu=0 Reason=Maintenance window [admin]
NodeName=unknown CPUTot=4 RealMemory=100 Gres=gpu:a100:2 State=MIXED Partitions=gpu AllocTRES=cpu=4
'''


CLUSTER_QUEUE = '''JobId=10 ArrayJobId=10 ArrayTaskId=0-8:2,10,12-14%3 ArrayTaskThrottle=3 JobState=PENDING Reason=Priority Partition=gpu,preempt AllocNode:Sid=x NumCPUs=8 CPUs/Task=4 MinMemoryCPU=4G TimeLimit=05:00:00 SubmitTime=2026-10-05T07:00:00 StartTime=2026-10-05T12:23:00 TresPerNode=gpu:a100:1
JobId=11 ArrayJobId=11 ArrayTaskId=1-20%2 JobState=PENDING Reason=JobArrayTaskLimit Partition=gpu NumCPUs=4 MinMemoryNode=32G TimeLimit=05:00:00 SubmitTime=2026-10-05T07:01:00 StartTime=Unknown TresPerNode=gpu:1 NtasksPerTRES:0
JobId=12 JobState=PENDING Reason=Dependency Partition=preempt NumCPUs=4 MinMemoryNode=32G TimeLimit=05:00:00 SubmitTime=2026-10-05T07:02:00 StartTime=Unknown TresPerNode=gpu:l40s:2
JobId=13 ArrayJobId=13 ArrayTaskId=0-2...%4 JobState=PENDING Reason=JobHeldUser Partition=gpu NumCPUs=4 MinMemoryNode=32G TimeLimit=05:00:00 SubmitTime=2026-10-05T07:03:00 StartTime=Unknown TresPerJob=gpu:h100:1
JobId=14 JobState=RUNNING Reason=None Partition=gpu TresPerNode=gpu:a100:1
JobId=15 JobState=PENDING Reason=BadConstraints Partition=gpu NumCPUs=4 MinMemoryNode=32G TimeLimit=05:00:00 SubmitTime=2026-10-05T07:04:00 StartTime=Unknown TRES=gres/gpu=1,gres/gpu:a100=1,gres/gpu:l40s=1 TresPerNode=gpu:a100:1
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
        self.stack.enter_context(patch('hendrix.gateway.gateway_options', return_value=[]))
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

    def test_named_submission_records_and_passes_slurm_name(self):
        capture = self.root / 'sbatch-args'
        sbatch = self.root / 'bin/sbatch'
        sbatch.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > ' + str(capture) + '\nprintf "12345\\n"\n')
        resources = dict(partition='gpu', model='a100', gpus=1, cpus=4, memory='32G', time='00:30:00')
        result = self.backend.submit(self.profile.presets[0], resources, run_name='mnist-mf-seed42')
        self.assertEqual(result['run_name'], 'mnist-mf-seed42--a100')
        self.assertEqual(result['preset_name'], 'smoke')
        self.assertIn('--job-name=mnist-mf-seed42--a100', capture.read_text().splitlines())
        with patch.object(self.backend, '_sync', side_effect=AssertionError('Must validate first')):
            with self.assertRaises(core.Error):
                self.backend.submit(self.profile.presets[0], resources, run_name='$(unsafe)')

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

    def test_compact_arrays_caps_and_unknown_ranges(self):
        for expression, expected in [('0-8:2,10,12-14%3', (9, 3)), ('[0-99999999%8]', (100000000, 8)),
                                     ('7', (1, None)), ('0-3...', (None, None)),
                                     ('0-3,2-5%2', (None, 2)), ('2-1', (None, None)),
                                     ('0-3:0', (None, None)), ('0-3%bad', (None, None))]:
            self.assertEqual(core.array_size(expression), expected)
        rows, warning = core.parse_cluster_queue(CLUSTER_QUEUE)
        self.assertEqual(len(rows), 5)
        self.assertIn('unknown', warning)
        array = rows[0]
        self.assertEqual(array['id'], '10_[0-8:2,10,12-14%3]')
        self.assertEqual((array['tasks'], array['cap'], array['memory']), (9, 3, '4G/CPU'))
        self.assertEqual(array['partition'], 'gpu,preempt')  # Colon/slash keys delimit fields.
        demand = core.pending_demand(rows)
        self.assertEqual(demand['a100']['tasks'], 10)
        self.assertEqual(demand['a100']['waiting'], 9)
        self.assertEqual(demand['a100']['other'], 1)
        self.assertEqual(demand['any']['tasks'], 20)
        self.assertNotIn('l40s', demand)
        self.assertTrue(demand['h100']['unknown'])
        self.assertIsNone(rows[3]['start'])
        self.assertEqual(core.pending_demand(rows, '*')['l40s']['blocked'], 1)
        duplicate, _ = core.parse_cluster_queue(CLUSTER_QUEUE + CLUSTER_QUEUE)
        self.assertEqual(len(duplicate), len(rows))
        partial, warning = core.parse_cluster_queue('unrecognised record\n' + CLUSTER_QUEUE)
        self.assertEqual(len(partial), 5)
        self.assertIn('could not be parsed', warning)
        concrete, _ = core.parse_cluster_queue('JobId=90 ArrayJobId=10 ArrayTaskId=8 JobState=PENDING Partition=gpu Reason=Resources TresPerTask=gpu:1')
        self.assertEqual(concrete[0]['id'], '10_8')
        self.assertEqual(concrete[0]['groups'], {'any'})
        unlimited, _ = core.parse_cluster_queue('JobId=20 ArrayJobId=20 ArrayTaskId=0-9 ArrayTaskThrottle=0 JobState=PENDING Partition=gpu Reason=Resources TresPerNode=gpu:1')
        self.assertEqual(core.cap_text(unlimited[0]), 'unlimited')
        self.assertEqual(core.cap_text(concrete[0]), '?')

    def test_blocked_reasons_and_untyped_demand(self):
        for reason, category in [('Resources', 'waiting'), ('Priority', 'waiting'),
                                 ('Dependency', 'blocked'), ('DependencyNeverSatisfied', 'blocked'),
                                 ('JobHeldUser', 'blocked'), ('JobHeldAdmin', 'blocked'),
                                 ('JobArrayTaskLimit', 'blocked'), ('BeginTime', 'blocked'),
                                 ('QOSMaxJobsPerUserLimit', 'other'), ('UnfamiliarReason', 'other')]:
            self.assertEqual(core.pending_reason(reason)[0], category)
        rows, _ = core.parse_cluster_queue('JobId=1 JobState=PENDING Partition=gpu Reason=Resources TRES=cpu=4,gres/gpu=1,gres/gpu:a100=1,gres/gpu:l40s=1\nJobId=2 JobState=PENDING Partition=gpu Reason=Dependency')
        demand = core.pending_demand(rows)
        self.assertEqual(set(demand), {'any', 'none'})
        self.assertEqual(demand['any']['tasks'], 1)

    def test_nominal_vram_and_variant_uncertainty(self):
        self.assertEqual(core.gpu_metadata('a100', 48)['assessment'], 'variant uncertain')
        self.assertEqual(core.gpu_metadata('A100', 40)['assessment'], 'likely fits by specification')
        self.assertEqual(core.gpu_metadata('a100', 81)['assessment'], 'too small')
        self.assertEqual(core.gpu_metadata('l40s', 48)['assessment'], 'likely fits by specification')
        self.assertEqual(core.gpu_metadata('a40', 49)['assessment'], 'too small')
        self.assertEqual(core.gpu_metadata('h100', 85)['assessment'], 'variant uncertain')
        self.assertEqual(core.gpu_metadata('quatrortx', 8)['assessment'], 'unknown')
        self.assertEqual(core.gpu_metadata('titanrtx', 24)['assessment'], 'likely fits by specification')
        self.assertEqual(core.gpu_metadata('l40s', '')['assessment'], 'unknown')
        self.assertTrue(core.gpu_metadata('l40s')['source'].startswith('https://www.nvidia.com/'))
        for bad in ['nan', 'inf', '-1', '0', '48G']:
            with self.assertRaises(core.Error):
                core.minimum_vram(bad)

    def test_observed_fit_requires_resources_on_one_healthy_node(self):
        nodes = core.parse_nodes('''NodeName=gpu-only Partitions=gpu State=MIXED CPUTot=16 CPUAlloc=15 RealMemory=65536 AllocMem=0 Gres=gpu:l40s:4 GresUsed=gpu:l40s:0
NodeName=ram-short Partitions=gpu State=IDLE CPUTot=16 CPUAlloc=0 RealMemory=65536 AllocMem=65000 Gres=gpu:l40s:4 GresUsed=gpu:l40s:0
NodeName=down Partitions=gpu State=IDLE+DRAIN CPUTot=16 CPUAlloc=0 RealMemory=65536 AllocMem=0 Gres=gpu:l40s:4 GresUsed=gpu:l40s:0
NodeName=other Partitions=private State=IDLE CPUTot=16 CPUAlloc=0 RealMemory=65536 AllocMem=0 Gres=gpu:l40s:4 GresUsed=gpu:l40s:0
''')
        resources = dict(partition='gpu', model='l40s', gpus=2, cpus=4, memory='32G', time='05:00:00')
        script = '#!/bin/bash\n#SBATCH -N1\n#SBATCH --ntasks=1\ntrue\n'
        fit = core.observed_fit(nodes, resources, script)
        self.assertIn('no observed fit', fit)
        self.assertIn('CPU', fit)
        self.assertIn('host RAM', fit)
        self.assertEqual(core.observed_fit(nodes[2:3], resources, script), 'no healthy inventoried nodes')
        nodes[0]['cpu_free'] = 4
        self.assertEqual(core.observed_fit(nodes, resources, script), 'fits on gpu-only')
        nodes[0]['cpu_free'] = None
        self.assertIn('unknown', core.observed_fit(nodes, resources, script))
        for directive in ['--nodes=2', '--ntasks=4', '-n4', '-Ca', '-wnode', '--constraint=a', '--exclusive', '--gpus-per-task=2', '--mem-per-cpu=8G', 'packjob']:
            self.assertIn('unknown', core.observed_fit(nodes, resources, '#!/bin/bash\n#SBATCH ' + directive + '\ntrue'))
        self.assertIsNone(core.script_fit_issue('#!/bin/bash\n#SBATCH --account=ml --qos=normal\ntrue\n#SBATCH -N2'))
        self.assertIn('unknown', core.script_fit_issue('#!/bin/sh\n#SLURM -N2\ntrue'))
        self.assertIn('unknown', core.script_fit_issue('#!/bin/sh\n#PBS -l nodes=2\ntrue'))

    def test_estimate_parsing_and_timezone_conversion(self):
        original = os.environ.get('TZ')
        try:
            os.environ['TZ'] = 'Europe/Copenhagen'
            time.tzset()
            value = core.parse_estimate('sbatch: Job 12 to start at 2026-10-05T12:23:00 using 4 processors')
            self.assertEqual(value.strftime('%H:%M %Z'), '14:23 CEST')
            self.assertEqual(core.slurm_time('2026-12-01T12:00:00').strftime('%H:%M %Z'), '13:00 CET')
            self.assertEqual(core.parse_estimate('StartTime=2026-10-05T12:23:00Z'), value)
            for unavailable in ['Unknown', 'N/A', 'allocation failure', 'start at 2026-99-01T00:00:00']:
                self.assertIsNone(core.parse_estimate(unavailable))
        finally:
            if original is None:
                os.environ.pop('TZ', None)
            else:
                os.environ['TZ'] = original
            time.tzset()

    def test_estimate_only_uses_local_script_and_shared_resource_flags(self):
        preset = dict(self.profile.presets[0], args=['a config.yml', '$(no-execution)'])
        script = '#!/bin/sh\n#SBATCH --account=ml\n#SBATCH --qos=normal\n#SBATCH --dependency=afterok:42\n#SBATCH --begin=16:00\ntrue\n'
        (self.source / preset['script']).write_text(script)
        request = dict(partition='gpu', model='a100', gpus=1, cpus=4, memory='32G', time='00:30:00')
        with patch.object(core.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '',
             'sbatch: Job 99 to start at 2026-10-05T12:23:00 using 4 processors\n__HENDRIX_START_EPOCH__1791202980')) as run, \
             patch.object(self.backend, 'submit', side_effect=AssertionError('submitted')), \
             patch.object(self.backend, '_sync', side_effect=AssertionError('synced')), \
             patch.object(self.backend, 'record', side_effect=AssertionError('history written')):
            estimate = self.backend.estimate(preset, request, self.backend.read_script(preset))
            self.assertIsNotNone(estimate['start'])
            self.assertEqual(run.call_args.kwargs['input'], script)
            command = run.call_args.args[0][-1]
            self.assertIn('sbatch --test-only', command)
            self.assertIn('/dev/stdin', command)
            self.assertIn("'a config.yml'", command)
            self.assertTrue(all(flag in command for flag in core.resource_flags(request)))
            self.assertNotIn('--parsable', command)
            self.assertNotIn('TZ=UTC', command)  # Preserve interpretation of wall-clock scheduling directives.
        self.assertFalse(self.remote.exists())
        self.assertFalse(core.STATE.exists())
        self.assertFalse(core.CONFIG.exists())
        for response in [subprocess.CompletedProcess([], 0, '', 'no estimate available'),
                         subprocess.CompletedProcess([], 1, '', 'allocation failure')]:
            with patch.object(core.subprocess, 'run', return_value=response):
                result = self.backend.estimate(preset, request, script)
                self.assertIsNone(result['start'])
                self.assertEqual(result['error'], response.returncode != 0)
        with patch.object(core.subprocess, 'run', side_effect=subprocess.TimeoutExpired('ssh', 30)):
            self.assertTrue(self.backend.estimate(preset, request, script)['error'])

    def test_guidance_compatibility_and_separation_from_slurm_resources(self):
        request = dict(partition='gpu', model='a100', gpus=1, cpus=4, memory='32G', time='00:30:00')
        key = core.launch_key(self.profile, self.profile.presets[0])
        core.atomic_json(core.CONFIG / 'launch-settings.json', dict(last_presets={}, requests={key: [request]}))
        self.assertEqual(core.load_launch_settings()['guidance'], {})
        core.remember_launch(self.profile, self.profile.presets[0], [request], '48.5')
        saved = core.load_launch_settings()
        self.assertEqual(saved['requests'][key], [request])
        self.assertEqual(saved['guidance'][key], {'minimum_vram': '48.5'})
        self.assertNotIn('vram', ' '.join(core.resource_flags(request)))

    def test_estimation_shell_preserves_script_and_converts_remote_timezone(self):
        sbatch = self.root / 'bin/sbatch'
        # Fake scheduler insists on stdin and the original directive; it never executes it.
        sbatch.write_text('''#!/bin/sh
case "$*" in *--test-only*'/dev/stdin'*) ;; *) exit 1;; esac
body=$(cat /dev/stdin)
case "$body" in *'#SBATCH --begin=16:00'*) ;; *) exit 2;; esac
printf 'sbatch: Job 123 to start at 2026-10-25T13:00:00 using 4 processors\\n' >&2
''')
        sbatch.chmod(0o755)
        self.profile.remote = str(self.source)
        request = dict(partition='gpu', model='a100', gpus=1, cpus=4, memory='32G', time='00:30:00')
        body = '#!/bin/sh\n#SBATCH --begin=16:00\ntouch must-not-exist\n'
        with patch.dict(os.environ, {'TZ': 'Europe/Copenhagen'}), \
             patch.object(self.backend, 'ssh_argv', side_effect=lambda command: ['bash', '-c', command]):
            estimate = self.backend.estimate(self.profile.presets[0], request, body)
        self.assertFalse(estimate['error'], estimate['detail'])
        self.assertIsNotNone(estimate['start'], estimate['detail'])
        self.assertEqual(estimate['start'].astimezone(dt.timezone.utc).hour, 12)  # Future date crosses DST.
        self.assertFalse((self.source / 'must-not-exist').exists())

    def test_connect_reuses_session_and_keys_without_keyring(self):
        config = subprocess.CompletedProcess([], 0, 'user fhz806\nhostname hendrixgate\n', '')
        for results in [[subprocess.CompletedProcess([], 0)],
                        [subprocess.CompletedProcess([], 1), config, subprocess.CompletedProcess([], 0)]]:
            with patch.object(core.subprocess, 'run', side_effect=results) as run, \
                 patch.object(core.shutil, 'which', side_effect=AssertionError('Keyring helper must not be consulted')):
                self.backend.connect()
            self.assertEqual(run.call_count, len(results))
            self.assertIn('check', run.call_args_list[0].args[0])
            if len(results) == 3:
                self.assertIn('BatchMode=yes', run.call_args.args[0])

    def ssh_login_results(self, *, user='fhz806', hostname='hendrixgate', available=0, login=0):
        return [subprocess.CompletedProcess([], 1),
                subprocess.CompletedProcess([], 0, f'user {user}\nhostname {hostname}\n', ''),
                subprocess.CompletedProcess([], 1),
                subprocess.CompletedProcess([], available),
                subprocess.CompletedProcess([], login, '', 'Permission denied' if login else '')]

    def test_connect_saved_password_has_one_prompt_and_no_secret_in_arguments(self):
        with patch.object(core.subprocess, 'run', side_effect=self.ssh_login_results()) as run, \
             patch.object(core.shutil, 'which', return_value='/desktop/hendrix-ssh-askpass'):
            self.backend.connect()
        self.assertEqual(run.call_count, 5)
        self.assertEqual(run.call_args_list[3].args[0], ['/desktop/hendrix-ssh-askpass', '--check'])
        args, kwargs = run.call_args.args[0], run.call_args.kwargs
        for option in ['PreferredAuthentications=password', 'NumberOfPasswordPrompts=1', 'PubkeyAuthentication=no', 'KbdInteractiveAuthentication=no']:
            self.assertIn(option, args)
        self.assertEqual(kwargs['stdin'], subprocess.DEVNULL)
        self.assertEqual(kwargs['env']['SSH_ASKPASS_REQUIRE'], 'force')
        self.assertEqual(kwargs['env']['SSH_ASKPASS'], '/desktop/hendrix-ssh-askpass')
        self.assertTrue(kwargs['capture_output'])
        self.assertFalse(any('PASSWORD' in key for key in kwargs['env'] if key not in os.environ))

    def test_rejected_saved_password_falls_back_to_one_manual_attempt(self):
        results = self.ssh_login_results(login=255) + [subprocess.CompletedProcess([], 0)]
        with patch.object(core.subprocess, 'run', side_effect=results) as run, \
             patch.object(core.shutil, 'which', return_value='/desktop/hendrix-ssh-askpass'):
            self.backend.connect()
        self.assertEqual(run.call_count, 6)
        self.assertEqual(run.call_args_list[4].kwargs['env']['SSH_ASKPASS_REQUIRE'], 'force')
        self.assertEqual(run.call_args.kwargs['env']['SSH_ASKPASS_REQUIRE'], 'never')
        self.assertNotIn('stdin', run.call_args.kwargs)
        self.assertIn('NumberOfPasswordPrompts=1', run.call_args.args[0])

    def test_no_saved_password_preserves_interactive_login(self):
        with patch.object(core.subprocess, 'run', side_effect=self.ssh_login_results(available=1)) as run, \
             patch.object(core.shutil, 'which', return_value='/desktop/hendrix-ssh-askpass'):
            self.backend.connect()
        self.assertEqual(run.call_args.kwargs['env']['SSH_ASKPASS_REQUIRE'], 'never')
        self.assertNotIn('stdin', run.call_args.kwargs)

    def test_keyring_timeout_falls_back_to_terminal(self):
        results = self.ssh_login_results()[:3] + [subprocess.TimeoutExpired(['askpass', '--check'], 25),
                                                subprocess.CompletedProcess([], 0)]
        with patch.object(core.subprocess, 'run', side_effect=results) as run, \
             patch.object(core.shutil, 'which', return_value='/desktop/hendrix-ssh-askpass'):
            self.backend.connect()
        self.assertEqual(run.call_count, 5)
        self.assertEqual(run.call_args.kwargs['env']['SSH_ASKPASS_REQUIRE'], 'never')

    def test_saved_login_timeout_checks_session_before_manual_fallback(self):
        for connected in [0, 1]:
            results = self.ssh_login_results()[:4] + [subprocess.TimeoutExpired(['ssh'], 30),
                subprocess.CompletedProcess([], connected)]
            if connected:
                results.append(subprocess.CompletedProcess([], 0))
            with patch.object(core.subprocess, 'run', side_effect=results) as run, \
                 patch.object(core.shutil, 'which', return_value='/desktop/hendrix-ssh-askpass'):
                self.backend.connect()
            self.assertEqual(run.call_count, 6 + connected)
            self.assertIn('check', run.call_args_list[5].args[0])
            if connected:
                self.assertEqual(run.call_args.kwargs['env']['SSH_ASKPASS_REQUIRE'], 'never')

    def test_failed_manual_password_is_reported_without_retry(self):
        results = self.ssh_login_results(login=255) + [subprocess.CompletedProcess([], 255)]
        with patch.object(core.subprocess, 'run', side_effect=results) as run, \
             patch.object(core.shutil, 'which', return_value='/desktop/hendrix-ssh-askpass'):
            with self.assertRaisesRegex(core.Error, 'SSH login failed'):
                self.backend.connect()
        self.assertEqual(run.call_count, 6)

    def test_gateway_failure_never_accesses_password(self):
        with patch.object(core.subprocess, 'run', side_effect=self.ssh_login_results()[:2]) as run, \
             patch('hendrix.gateway.gateway_options', side_effect=core.Error('No SSH gateway responded')), \
             patch.object(core.shutil, 'which', side_effect=AssertionError('Unexpected password lookup')):
            with self.assertRaisesRegex(core.Error, 'No SSH gateway'):
                self.backend.connect()
        self.assertEqual(run.call_count, 2)

    def test_selected_gateway_is_used_for_login_and_remote_commands(self):
        proxy = ['-o', 'ProxyCommand=/bin/nc -F -w 8 192.0.2.2 22', '-o', 'ProxyUseFdpass=yes']
        with patch.object(core.subprocess, 'run', side_effect=self.ssh_login_results()) as run, \
             patch('hendrix.gateway.gateway_options', return_value=proxy), \
             patch.object(core.shutil, 'which', return_value='/desktop/hendrix-ssh-askpass'):
            self.backend.connect()
        self.assertIn(proxy[1], run.call_args.args[0])
        self.assertIn(proxy[1], self.backend.ssh_argv('true'))
        self.assertEqual(self.backend.ssh_argv('true')[-2:], ['hendrix', 'true'])
        self.assertIn('hendrix-control/%C', ' '.join(self.backend.options))

    def test_reconfigured_hendrix_never_reads_shared_password(self):
        for user, hostname in [('other', 'hendrixgate'), ('fhz806', 'other.example')]:
            results = self.ssh_login_results(user=user, hostname=hostname)
            # The fourth call is the ordinary interactive login, not the helper.
            results = results[:3] + [subprocess.CompletedProcess([], 0)]
            with patch.object(core.subprocess, 'run', side_effect=results) as run, \
                 patch.object(core.shutil, 'which', return_value='/desktop/hendrix-ssh-askpass'):
                self.backend.connect()
            self.assertEqual(run.call_count, 4)
            self.assertTrue(all(call.args[0][0] == 'ssh' for call in run.call_args_list))

    def test_other_hosts_and_background_queries_do_not_access_keyring(self):
        self.profile.host = 'other-cluster'
        with patch.object(core.subprocess, 'run', side_effect=[subprocess.CompletedProcess([], rc) for rc in [1, 1, 0]]), \
             patch.object(core.shutil, 'which', side_effect=AssertionError('Unexpected password lookup')):
            self.backend.connect()
        backend = core.Backend(self.profile)
        with patch.object(core.subprocess, 'run', return_value=subprocess.CompletedProcess([], 255, '', 'No connection')) as run, \
             patch.object(core.shutil, 'which', side_effect=AssertionError('Unexpected password lookup')):
            with self.assertRaises(core.Error):
                backend.nodes()
            self.assertIn('BatchMode=yes', run.call_args.args[0])
            self.assertNotIn('env', run.call_args.kwargs)


class LoginTests(unittest.TestCase):
    def setUp(self):
        # Offline login tests must never read the user's real authenticator.
        patcher = patch.object(vpn, 'lookup_totp', return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_keyring_lookup_timeout_returns_to_interactive_login(self):
        with patch.object(vpn, 'run', side_effect=subprocess.TimeoutExpired(['secret-tool'], 20)) as run:
            self.assertIsNone(vpn.lookup())
        self.assertEqual(run.call_args.kwargs['timeout'], 20)

    def test_ssh_askpass_only_supplies_password_to_matching_account(self):
        for prompt in ["fhz806@hendrixgate's password: ", "fhz806@hendrixgate.science.ku.dk's password:"]:
            output = io.StringIO()
            with patch.object(vpn, 'lookup', return_value='test-secret') as lookup, patch.object(vpn.sys, 'stdout', output):
                self.assertEqual(vpn.ssh_askpass(prompt), 0)
            self.assertEqual(output.getvalue(), 'test-secret\n')
            lookup.assert_called_once()
        for prompt in ["fhz806@other.example's password:", "other@hendrixgate's password:",
                       "Enter passphrase for key '/home/user/.ssh/id_ed25519':", 'Verification code:',
                       'Are you sure you want to continue connecting (yes/no)?', 'Password:']:
            with patch.object(vpn, 'lookup', side_effect=AssertionError('Secret lookup for unexpected prompt')):
                self.assertEqual(vpn.ssh_askpass(prompt), 1)

    def test_ssh_askpass_check_does_not_print_secret(self):
        for secret, code in [('test-secret', 0), (None, 1), ('bad\nsecret', 1), ('bad\x00secret', 1)]:
            output = io.StringIO()
            with patch.object(vpn, 'lookup', return_value=secret), patch.object(vpn.sys, 'stdout', output):
                self.assertEqual(vpn.ssh_askpass('--check'), code)
                self.assertEqual(output.getvalue(), '')

    def test_vpn_waits_for_dns_without_reauthenticating(self):
        with patch.object(vpn, 'run', return_value=subprocess.CompletedProcess([], 0)) as run, \
             patch.object(vpn, 'ready', side_effect=[False, False, True]), \
             patch.object(vpn, 'managed_pid', side_effect=[None, 123]), \
             patch.object(vpn, 'lookup', return_value=None), \
             patch.object(vpn.time, 'sleep'), \
             patch.object(vpn, 'authenticate', return_value=subprocess.CompletedProcess([], 0, stdout='cookie')) as auth, \
             patch.object(vpn, 'down') as down:
            vpn.up()
            auth.assert_called_once()
            down.assert_not_called()
            self.assertFalse(any('tailscale' in call.args[0] or 'resolvconf' in call.args[0]
                                 for call in run.call_args_list))

    def test_vpn_requires_split_dns_before_authentication(self):
        with patch.object(vpn, 'ready', return_value=False), \
             patch.object(vpn, 'managed_pid', return_value=None), \
             patch.object(vpn, 'run', return_value=subprocess.CompletedProcess([], 3)) as run, \
             patch.object(vpn, 'authenticate') as auth:
            with self.assertRaisesRegex(core.Error, 'systemd-resolved'):
                vpn.up()
            auth.assert_not_called()
            run.assert_called_once_with(['systemctl', 'is-active', '--quiet', 'systemd-resolved.service'])

    def test_existing_ku_network_needs_no_dns_changes(self):
        with patch.object(vpn, 'ready', return_value=True), patch.object(vpn, 'run') as run:
            vpn.up()
            run.assert_not_called()

    def test_dns_timeout_cleans_up_connection(self):
        with patch.object(vpn, 'run', return_value=subprocess.CompletedProcess([], 0)), \
             patch.object(vpn, 'ready', return_value=False), \
             patch.object(vpn, 'managed_pid', return_value=None), \
             patch.object(vpn, 'lookup', return_value=None), \
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

    def test_disconnect_only_stops_its_own_vpn(self):
        events = []
        def run(args, **kwargs):
            events.append(args)
            return subprocess.CompletedProcess(args, 0)
        with patch.object(vpn, 'managed_pid', return_value=123), \
             patch.object(Path, 'exists', return_value=False), \
             patch.object(vpn, 'run', side_effect=run):
            vpn.down()
        self.assertEqual(events, [['sudo', 'kill', '-INT', '123']])

    def test_disconnect_preserves_dns_if_tunnel_is_still_running(self):
        with patch.object(vpn, 'managed_pid', return_value=123), \
             patch.object(Path, 'exists', return_value=True), \
             patch.object(vpn.time, 'sleep'), \
             patch.object(vpn, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            with self.assertRaisesRegex(core.Error, 'has not stopped'):
                vpn.down()
            self.assertEqual(run.call_count, 1)

    def test_failed_authentication_is_not_retried(self):
        with patch.object(vpn, 'run', return_value=subprocess.CompletedProcess([], 0)), \
             patch.object(vpn, 'ready', return_value=False), patch.object(vpn, 'managed_pid', return_value=None), \
             patch.object(vpn, 'lookup', return_value='very-secret'), \
             patch.object(vpn, 'authenticate', return_value=subprocess.CompletedProcess([], 1, stdout='')) as auth:
            with self.assertRaises(core.Error):
                vpn.up()
            auth.assert_called_once()
            self.assertNotIn('very-secret', ' '.join(auth.call_args.args[0]))

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

    def test_disconnect_without_vpn_leaves_dns_alone(self):
        with patch.object(vpn, 'managed_pid', return_value=None), \
             patch.object(Path, 'exists', return_value=False), patch.object(vpn, 'run') as run:
            vpn.down()
            run.assert_not_called()


class TUITests(unittest.IsolatedAsyncioTestCase):
    async def test_number_sections_and_gpu_form_keyboard(self):
        with tempfile.TemporaryDirectory() as d, patch.object(core, 'CONFIG', Path(d)/'config'), \
             patch.object(core, 'STATE', Path(d)/'state'), patch.object(Path, 'home', return_value=Path(d)):
            app = HendrixApp()
            with patch.object(core.Backend, 'remote', side_effect=AssertionError('Unexpected network call')):
                async with app.run_test(size=(80, 24)) as pilot:
                    app.nodes = core.parse_nodes(NODES)
                    app.render_nodes()
                    for key, pane, target in [('3', 'project-tab', 'sync'), ('4', 'jobs-tab', 'jobs'),
                                               ('5', 'jobs-tab', 'job-log'), ('6', 'queue-tab', 'cluster-queue'), ('1', 'gpu-tab', 'models'),
                                               ('2', 'gpu-tab', 'nodes')]:
                        await pilot.press(key)
                        self.assertEqual(app.query_one(TabbedContent).active, pane)
                        self.assertEqual(app.focused.id, target)
                    await pilot.press('/', '1', '2', '3')
                    self.assertEqual(app.query_one('#node-filter', Input).value, '123')
                    app.query_one('#node-filter', Input).value = ''
                    await pilot.press('escape', '1', 'v', 'j', 'v', 'b')
                    await pilot.pause()
                    form = app.screen
                    self.assertIsInstance(form, SubmitForm)
                    rendered = '\n'.join(strip.text for strip in form._compositor.render_strips())
                    for label in ('Run', 'Smoke', 'Advanced settings', 'Review request'):
                        self.assertIn(label, rendered)
                    table = form.query_one('#submit-gpus', GPUChoices)
                    self.assertEqual(form.counts, {'h100': 1, 'a100': 1})
                    self.assertTrue(form.query_one('#advanced', Collapsible).collapsed)
                    await pilot.press('l', 'l', 'l', 'l', 'l')
                    self.assertEqual(form.counts['h100'], 4)
                    await pilot.press('j', 'l', 'h')
                    self.assertEqual(form.counts['a100'], 1)
                    await pilot.press('space')
                    self.assertEqual(form.counts['a100'], 0)
                    await pilot.press('space', 'G')
                    self.assertEqual(table.cursor_row, table.row_count - 1)
                    await pilot.press('g')
                    self.assertEqual(table.cursor_row, 0)
                    await pilot.press('a')
                    self.assertFalse(form.query_one('#advanced', Collapsible).collapsed)
                    cpus = form.query_one('#resource-cpus', Input)
                    cpus.focus()
                    await pilot.press('ctrl+a', 'ctrl+k', '8')
                    self.assertEqual(cpus.value, '8')
                    self.assertEqual(app.query_one(TabbedContent).active, 'gpu-tab')
                    await pilot.press('escape', 'a', 'ctrl+enter')
                    await pilot.pause()
                    self.assertIsInstance(app.screen, Confirm)
                    await pilot.press('escape')
                    await pilot.pause()
                    self.assertFalse(app.busy)
                    self.assertFalse((core.CONFIG / 'launch-settings.json').exists())

    async def test_multiple_gpu_jobs_saved_defaults_and_partial_failure(self):
        with tempfile.TemporaryDirectory() as d, patch.object(core, 'CONFIG', Path(d)/'config'), \
             patch.object(core, 'STATE', Path(d)/'state'), patch.object(Path, 'home', return_value=Path(d)):
            app = HendrixApp()
            submitted = dict(job_id='123', snapshot='/snapshot', output='/logs')
            with patch.object(core.Backend, 'remote', side_effect=AssertionError('Unexpected network call')), \
                 patch.object(core.Backend, 'submit', return_value=submitted) as submit, \
                 patch.object(HendrixApp, 'refresh_data'):
                async with app.run_test(size=(110, 45)) as pilot:
                    app.nodes = core.parse_nodes(NODES)
                    app.render_nodes()
                    app.marked_rows = {('hendrixgpu16fl', 'h100'), ('hendrixgpu01fl', 'a100')}
                    await pilot.press('3', 'b')
                    await pilot.pause()
                    form = app.screen
                    await pilot.press('l', 'j', 'l')
                    form.query_one('#resource-cpus', Input).value = '12'
                    form.query_one('#resource-time', Input).value = '02:00:00'
                    await pilot.press('ctrl+enter')
                    await pilot.pause()
                    await pilot.press('enter')
                    await pilot.pause(.3)
                    self.assertEqual(submit.call_count, 2)
                    requests = [call.args[1] for call in submit.call_args_list]
                    self.assertEqual({r['model']: r['gpus'] for r in requests}, {'h100': 2, 'a100': 2})
                    self.assertTrue(all(r['cpus'] == 12 for r in requests))
                    app.marked_rows.clear()
                    await pilot.press('b')
                    await pilot.pause()
                    form = app.screen
                    self.assertEqual(form.counts, {'h100': 2, 'a100': 2})
                    self.assertEqual(form.query_one('#resource-cpus', Input).value, '12')
                    self.assertEqual(form.query_one('#resource-time', Input).value, '02:00:00')
                    preset = form.query_one('#preset', Select)
                    preset.value = 1
                    await pilot.pause()
                    self.assertEqual(form.query_one('#resource-time', Input).value, '05:00:00')
                    self.assertEqual(form.query_one('#resource-cpus', Input).value, '4')
                    preset.value = 0
                    await pilot.pause()
                    self.assertEqual(form.query_one('#resource-cpus', Input).value, '12')
                    submit.reset_mock()
                    submit.side_effect = [submitted, core.UncertainSubmission('lost response')]
                    form.query_one('#submit-gpus', GPUChoices).focus()
                    await pilot.press('G', 'k', 'space', 'b')
                    await pilot.pause()
                    await pilot.press('enter')
                    await pilot.pause(.3)
                    self.assertEqual(submit.call_count, 2)
                    self.assertFalse(app.busy)
                    saved = core.load_launch_settings()
                    remembered = saved['requests'][core.launch_key(app.profile, app.profile.presets[0])]
                    self.assertEqual(remembered[:2], requests)
                    self.assertEqual(len(remembered), 3)
                    self.assertEqual(remembered[2]['model'], 'titan')

    async def test_preset_settings_survive_reopening_and_validation(self):
        with tempfile.TemporaryDirectory() as d, patch.object(core, 'CONFIG', Path(d)/'config'):
            profile = core.seed_profile()
            requests = [dict(model='a100', gpus=3, partition='gpu', cpus=16, memory='64G', time='06:00:00')]
            core.remember_launch(profile, profile.presets[1], requests)
            form = SubmitForm(profile, ['a100', 'h100'], chosen='h100')
            self.assertEqual(form.preset_index, 1)
            self.assertEqual(form.counts, {'a100': 3})
            self.assertEqual(form.defaults(1)['memory'], '64G')
            marked = SubmitForm(profile, ['a100', 'h100'], selected=['h100'])
            self.assertEqual(marked.counts, {'h100': 1})
            profile.remote = '~/different-project'
            self.assertEqual(SubmitForm(profile, ['a100']).preset_index, 0)
            self.assertEqual(SubmitForm(profile, ['a100']).defaults(1)['cpus'], 4)
            core.atomic_json(core.CONFIG / 'launch-settings.json', {
                'last_presets': {}, 'requests': {'bad': [dict(requests[0], gpus='3')]}})
            with self.assertRaises(core.Error):
                SubmitForm(profile, ['a100'])

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
                    self.assertEqual(len(models.columns), 7)
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
                if command == 'TZ=UTC SLURM_BITSTR_LEN=4096 scontrol show jobs -o':
                    return CLUSTER_QUEUE
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

    async def test_cluster_queue_keyboard_cached_filtering_sort_and_partial_refresh(self):
        with tempfile.TemporaryDirectory() as d, patch.object(core, 'CONFIG', Path(d)/'config'), \
             patch.object(core, 'STATE', Path(d)/'state'), patch.object(Path, 'home', return_value=Path(d)):
            app = HendrixApp()
            with patch.object(app.backend, 'jobs', return_value=[]), \
                 patch.object(app.backend, 'nodes', return_value=core.parse_nodes(NODES)), \
                 patch.object(app.backend, 'cluster_queue', return_value=core.parse_cluster_queue(CLUSTER_QUEUE)) as query:
                async with app.run_test(size=(80, 30)) as pilot:
                    app.action_refresh()
                    await pilot.pause(.3)
                    await pilot.press('6')
                    table = app.query_one('#cluster-queue', DataTable)
                    self.assertEqual(app.focused, table)
                    self.assertEqual(table.row_count, 4)
                    self.assertIn('Any GPU: 20', str(app.query_one('#queue-summary').render()))
                    await pilot.press('j')
                    chosen = app.table_row_key(table)
                    app.render_cluster_queue()
                    self.assertEqual(app.table_row_key(table), chosen)
                    await pilot.press('/', 'a', '1', '0', '0')
                    self.assertEqual(table.row_count, 2)
                    await pilot.press('escape')
                    app.query_one('#queue-filter', Input).value = ''
                    app.query_one('#queue-partition', Select).value = '*'
                    await pilot.pause()
                    self.assertEqual(table.row_count, 5)
                    self.assertEqual(query.call_count, 1)  # Entire filtering/sorting is local.
                    await pilot.resize_terminal(60, 24)
                    await pilot.pause()
                    self.assertLessEqual(app.query_one('#queue-partition').region.right, 60)
                    self.assertGreater(table.row_count, 0)
                    app.query_one('#state-filter', Select).value = 'all'
                    app.sort_key = 'pending'
                    app.sort_reverse = False
                    app.render_nodes()
                    models = app.query_one('#models', DataTable)
                    self.assertEqual(str(models.get_row_at(models.row_count - 1)[0]), 'h100')
                    self.assertEqual(str(models.get_cell('a100', 'pending')), '10')
                    self.assertEqual(str(models.get_cell('h100', 'pending')), '?')
                    self.assertEqual(str(models.get_cell('a100', 'vram')), '40/80 GB')
                    old = app.cluster_jobs
                    with patch.object(app.backend, 'cluster_queue', side_effect=core.Error('queue permission denied')):
                        app.action_refresh()
                        await pilot.pause(.3)
                        self.assertTrue(app.connected)
                        self.assertIs(app.cluster_jobs, old)
                        self.assertIn('stale: queue permission denied', app.queue_freshness())
                        self.assertEqual(app.query_one('#nodes', DataTable).row_count, 6)
                    # A failed inventory/personal query does not discard a working queue.
                    with patch.object(app.backend, 'nodes', side_effect=core.Error('inventory failed')), \
                         patch.object(app.backend, 'jobs', side_effect=core.Error('personal jobs failed')):
                        app.action_refresh()
                        await pilot.pause(.3)
                        self.assertTrue(app.connected)
                        self.assertEqual(app.query_one('#cluster-queue', DataTable).row_count, 5)

    async def test_comparison_only_queries_on_press_invalidates_and_explicitly_selects(self):
        with tempfile.TemporaryDirectory() as d, patch.object(core, 'CONFIG', Path(d)/'config'), \
             patch.object(core, 'STATE', Path(d)/'state'), patch.object(Path, 'home', return_value=Path(d)):
            app = HendrixApp()
            local = Path(d) / 'project'
            local.mkdir()
            script = local / 'train.sbatch'
            script.write_text('#!/bin/sh\n#SBATCH --nodes=1\n#SBATCH --ntasks=1\ntrue\n')
            app.profile.local = str(local)
            app.profile.presets = [dict(name='Train', script='train.sbatch', args=['config.yml'], time='05:00:00')]
            start = dt.datetime(2026, 10, 5, 12, tzinfo=dt.timezone.utc).astimezone()
            def estimate(preset, resources, body):
                if resources['model'] == 'l40s':
                    return dict(start=start, at=start, detail='earlier estimate', error=False)
                if resources['model'] == 'a100':
                    return dict(start=start - dt.timedelta(hours=1), at=start, detail='ambiguous memory', error=False)
                return dict(start=None, at=start, detail='allocation failure', error=True)
            with patch.object(app.backend, 'estimate', side_effect=estimate) as estimates, \
                 patch.object(app.backend, 'submit', side_effect=AssertionError('Unexpected submission')), \
                 patch.object(app.backend, 'sync', side_effect=AssertionError('Unexpected sync')), \
                 patch.object(app.backend, 'record', side_effect=AssertionError('Unexpected history write')), \
                 patch.object(app.backend, 'remote', side_effect=AssertionError('Unexpected inventory query')):
                async with app.run_test(size=(80, 30)) as pilot:
                    app.nodes = core.parse_nodes(NODES)
                    app.nodes += core.parse_nodes('NodeName=l40 Partitions=gpu State=IDLE CPUTot=8 CPUAlloc=0 RealMemory=65536 AllocMem=0 Gres=gpu:l40s:4 GresUsed=gpu:l40s:0')
                    app.cluster_jobs, _ = core.parse_cluster_queue(CLUSTER_QUEUE)
                    app.render_nodes()
                    await pilot.press('1', 'b')
                    await pilot.pause()
                    form = app.screen
                    original_counts = form.counts.copy()
                    form.query_one('#minimum-vram', Input).value = '48'
                    await pilot.pause()
                    await pilot.press('c')
                    await pilot.pause()
                    comparison = app.screen
                    self.assertIsInstance(comparison, CompareGPUs)
                    self.assertEqual(estimates.call_count, 0)
                    self.assertEqual(comparison.count, '1')
                    table = comparison.query_one('#comparison', DataTable)
                    self.assertEqual(table.row_count, 5)  # Includes models with no currently free capacity.
                    self.assertEqual(str(table.get_cell('a100', 'memory')), 'variant uncertain')
                    await pilot.press('c')
                    await pilot.pause(.3)
                    self.assertEqual(estimates.call_count, 5)
                    self.assertEqual(str(table.get_cell('l40s', 'model')), 'l40s ★')
                    self.assertEqual(str(table.get_cell('a100', 'model')), 'a100')
                    self.assertEqual(str(table.get_cell('h100', 'start')), 'scheduler error')
                    table.move_cursor(row=comparison.models.index('l40s'))
                    comparison.render_comparison()
                    self.assertEqual(comparison.current_model(), 'l40s')
                    comparison.query_one('#compare-count', Input).value = '2'
                    await pilot.pause()
                    self.assertEqual(comparison.estimates, {})
                    await pilot.press('c')
                    await pilot.pause(.3)
                    self.assertEqual(estimates.call_count, 10)
                    self.assertTrue(all(call.args[1]['gpus'] == 2 for call in estimates.call_args_list[-5:]))
                    script.write_text(script.read_text() + '# changed\n')
                    comparison.check_script()
                    self.assertEqual(comparison.estimates, {})
                    self.assertIn('Script changed', comparison.state)
                    await pilot.resize_terminal(60, 24)
                    await pilot.pause()
                    self.assertLessEqual(comparison.query_one('#dialog').region.right, 60)
                    self.assertEqual(form.counts, original_counts)
                    await pilot.press('u')
                    await pilot.pause()
                    self.assertIs(app.screen, form)
                    self.assertEqual(form.counts, {'l40s': 2})
                    self.assertEqual(form.minimum_vram, '48')
                    await pilot.press('escape')
                    await pilot.pause()
                    self.assertFalse(app.busy)
                    self.assertFalse((core.CONFIG / 'launch-settings.json').exists())
                    self.assertFalse(core.STATE.exists())

    async def test_comparison_discards_estimates_when_script_changes_during_query(self):
        with tempfile.TemporaryDirectory() as d, patch.object(core, 'CONFIG', Path(d)/'config'), \
             patch.object(core, 'STATE', Path(d)/'state'), patch.object(Path, 'home', return_value=Path(d)):
            app = HendrixApp()
            script = Path(d) / 'train.sbatch'
            script.write_text('#!/bin/sh\ntrue\n')
            profile = core.Profile('test', d, '~/test', presets=[dict(name='Train', script='train.sbatch')])
            backend = core.Backend(profile)
            def estimate(*_):
                script.write_text('#!/bin/sh\n#SBATCH --ntasks=2\ntrue\n')
                now = dt.datetime.now().astimezone()
                return dict(start=now, at=now, detail='old script', error=False)
            with patch.object(backend, 'estimate', side_effect=estimate):
                async with app.run_test(size=(100, 35)) as pilot:
                    dialog = CompareGPUs(backend, profile.presets[0],
                        dict(partition='gpu', cpus=4, memory='32G', time='05:00:00'), 1, '', core.parse_nodes(NODES), None)
                    app.push_screen(dialog)
                    await pilot.pause()
                    await pilot.press('c')
                    await pilot.pause(.3)
                    self.assertEqual(dialog.estimates, {})
                    self.assertIn('Script changed', dialog.state)
                    self.assertIn('unknown', str(dialog.query_one('#comparison').get_cell('h100', 'fit')))
                    await pilot.press('escape')


if __name__ == '__main__':
    unittest.main()
