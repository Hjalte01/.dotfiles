"""Profiles, conservative SSH/Slurm queries, and isolated job source snapshots."""
from __future__ import annotations

import contextlib
import dataclasses
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import tempfile
import uuid

CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'hendrix'
STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'hendrix'
EXCLUDES = ['.git/', '.venv*/', 'venv/', '__pycache__/', 'data/', 'datasets/',
            'checkpoints/', 'results/runs/', '*.out', '.hendrix/']
SHARED = ['data', 'datasets', 'checkpoints', 'results']
ROOT = '/home/hjalte/Documents/study/ATDL/Assignments/code/ATDL-MeanFlow-Reproduction'


class Error(RuntimeError):
    pass


class UncertainSubmission(Error):
    """The scheduler may have accepted the job; never retry automatically."""


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.write-')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def relative_path(value: str) -> str:
    p = PurePosixPath(value)
    if not value or p.is_absolute() or '..' in p.parts or str(p) == '.' or '\n' in value:
        raise Error(f'Expected a project-relative path: {value!r}')
    if p.parts[0] == '.hendrix':
        raise Error('Shared paths and scripts cannot point into .hendrix.')
    return str(p)


@dataclasses.dataclass
class Profile:
    name: str
    local: str
    remote: str
    host: str = 'hendrix'
    excludes: list[str] = dataclasses.field(default_factory=lambda: EXCLUDES.copy())
    shared: list[str] = dataclasses.field(default_factory=lambda: SHARED.copy())
    presets: list[dict] = dataclasses.field(default_factory=list)
    venv: str = '.venv-hendrix'

    def validate(self):
        if not self.name or not re.fullmatch(r'[A-Za-z0-9_.-]+', self.host) or self.host.startswith('-'):
            raise Error('Profile needs a name and a simple SSH host alias.')
        if not Path(self.local).expanduser().is_absolute():
            raise Error('Local project path must be absolute.')
        if not (self.remote.startswith('/') or self.remote.startswith('~/')):
            raise Error('Remote project root must start with / or ~/.')
        if any(c in self.remote for c in '\n\r\x00') or '..' in PurePosixPath(self.remote).parts:
            raise Error('Remote root contains unsupported path components.')
        if self.remote.rstrip('/') in ('/', '~', ''):
            raise Error('Use a dedicated remote project directory, not your home or /.')
        if any(not isinstance(values, list) or any(not isinstance(v, str) for v in values)
               for values in (self.excludes, self.shared)):
            raise Error('Exclusions and shared paths must be lists of strings.')
        if not isinstance(self.presets, list):
            raise Error('Batch presets must be a list.')
        for path in [*self.shared, self.venv]:
            relative_path(path)
        normalized = sorted(str(PurePosixPath(p)) for p in [*self.shared, self.venv])
        if len(set(normalized)) != len(normalized):
            raise Error('Shared paths must not be duplicated.')
        for left, right in zip(normalized, normalized[1:]):
            if right.startswith(left + '/'):
                raise Error('Shared paths must not overlap.')
        for preset in self.presets:
            relative_path(preset['script'])
            if not isinstance(preset.get('args', []), list):
                raise Error('Preset args must be a JSON list.')
        return self


def seed_profile():
    return Profile('MeanFlow', ROOT, '~/projects/ATDL-MeanFlow-Reproduction', presets=[
        dict(name='Smoke', script='scripts/hendrix/smoke.sbatch', args=[], time='00:30:00'),
        dict(name='Train', script='scripts/hendrix/train.sbatch',
             args=['configs/hendrix_b4.yml'], time='05:00:00')])


def load_profiles(path: Path | None = None) -> list[Profile]:
    path = path or CONFIG / 'profiles.json'
    if not path.exists():
        save_profiles([seed_profile()], path)
    try:
        raw = json.loads(path.read_text())
        if not isinstance(raw, dict):
            raise Error('Profiles must be a JSON object with version and projects fields.')
        if raw.get('version') != 1:
            raise Error('Unsupported profile version; expected version 1.')
        profiles = [Profile(**p).validate() for p in raw['projects']]
        if not profiles or len({p.name for p in profiles}) != len(profiles):
            raise Error('Provide at least one project with unique project names.')
        return profiles
    except (ValueError, KeyError, TypeError) as exc:
        raise Error(f'Invalid profile file {path}: {exc}') from exc


def save_profiles(profiles, path=None):
    atomic_json(path or CONFIG / 'profiles.json',
                dict(version=1, projects=[dataclasses.asdict(p.validate()) for p in profiles]))


def fields(line: str) -> dict[str, str]:
    matches = list(re.finditer(r'(?:^|\s)([A-Za-z][A-Za-z0-9_]*)=', line))
    return {m[1]: line[m.end():matches[i + 1].start() if i + 1 < len(matches) else len(line)].strip()
            for i, m in enumerate(matches)}


def gpu_counts(value: str) -> dict[str, int]:
    # Slurm appends topology / allocated index annotations to typed GRES.
    return {m[1] or 'untyped': int(m[2]) for m in re.finditer(
        r'(?:^|,)gpu:(?:([^:,()]+):)?(\d+)(?:\([^)]*\))?', value)}


def tres(value: str) -> dict[str, str]:
    return dict(item.split('=', 1) for item in value.split(',') if '=' in item)


def integer(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def memory_mib(value):
    match = re.fullmatch(r'(\d+(?:\.\d+)?)([KMGTP]?)', str(value), re.I)
    if not match:
        return None
    scale = {'K': 1 / 1024, '': 1, 'M': 1, 'G': 1024, 'T': 1024 ** 2, 'P': 1024 ** 3}
    return int(float(match[1]) * scale[match[2].upper()])


def free_total(free, total, *, gib=False):
    def display(value):
        if value is None:
            return '?'
        if not gib:
            return str(value)
        value /= 1024
        return str(int(value)) if value.is_integer() else f'{value:.1f}'
    return f'{display(free)}({display(total)})'


def parse_nodes(output: str) -> list[dict]:
    nodes = {}
    for line in output.splitlines():
        f = fields(line)
        if 'NodeName' not in f:
            continue
        capacity = gpu_counts(f.get('Gres', ''))
        used = gpu_counts(f.get('GresUsed', ''))
        allocated = tres(f.get('AllocTRES', ''))
        by_model = {}
        for model in capacity:
            value = used.get(model)
            typed = allocated.get('gres/gpu:' + model)
            total = allocated.get('gres/gpu')
            if value is None and typed is not None:
                value = int(typed)
            if value is None and total is not None and (len(capacity) == 1 or int(total) == 0):
                value = int(total)
            # A present GresUsed field with explicit zero GPU counts is authoritative.
            by_model[model] = value
        state = f.get('State', 'UNKNOWN')
        eligible = bool(re.match(r'^(IDLE|MIXED|ALLOCATED)(?:\+|$)', state)) and not any(
            bad in state for bad in ('DRAIN', 'DOWN', 'FAIL', 'NO_RESPOND', 'RESERVED', 'MAINT', 'COMPLETING', 'POWER', 'REBOOT', 'PLANNED', 'BLOCKED'))
        cpu_total = integer(f.get('CPUEfctv', f.get('CPUTot')))
        cpu_used = integer(f.get('CPUAlloc', allocated.get('cpu')))
        ram_total = memory_mib(f.get('RealMemory'))
        ram_used = memory_mib(f.get('AllocMem', allocated.get('mem')))
        cpu_free = max(0, cpu_total - cpu_used) if cpu_total is not None and cpu_used is not None else None
        ram_free = max(0, ram_total - ram_used) if ram_total is not None and ram_used is not None else None
        reason = f.get('Reason', '')
        if reason.strip().lower() in ('(null)', 'none', 'null', 'n/a', 'not set'):
            reason = ''
        nodes[f['NodeName']] = dict(name=f['NodeName'], state=state, capacity=capacity,
            used=by_model, eligible=eligible, partitions=f.get('Partitions', '?'),
            cpus=f.get('CPUTot', '?'), memory=f.get('RealMemory', '?'), reason=reason,
            cpu_total=cpu_total, cpu_free=cpu_free, ram_total=ram_total, ram_free=ram_free)
    return list(nodes.values())


def summarize(nodes: list[dict]) -> list[dict]:
    result = {}
    for node in nodes:
        for model, count in node['capacity'].items():
            r = result.setdefault(model, dict(model=model, total=0, used=0, unallocated=0,
                                               usable=0, unknown=False, usable_unknown=False,
                                               cpu_total=0, cpu_free=0, ram_total=0, ram_free=0,
                                               cpu_total_unknown=False, cpu_free_unknown=False,
                                               ram_total_unknown=False, ram_free_unknown=False))
            for resource in ('cpu_total', 'cpu_free', 'ram_total', 'ram_free'):
                value = node.get(resource)
                if value is None:
                    r[resource + '_unknown'] = True
                else:
                    r[resource] += value
            r['total'] += count
            used = node['used'][model]
            if used is None:
                r['unknown'] = True
                if node['eligible']:
                    r['usable_unknown'] = True
            else:
                r['used'] += used
                r['unallocated'] += max(0, count - used)
                if node['eligible']:
                    r['usable'] += max(0, count - used)
    return sorted(result.values(), key=lambda row: row['model'])


# A UI preference, not a benchmark ranking or a scheduling guarantee.
GPU_PREFERENCE = {'h100': 0, 'a100': 1, 'l40s': 2, 'a40': 3,
                  'titanrtx': 4, 'quatrortx': 4, 'titanx': 5, 'titan': 6}


def visible_gpu_nodes(nodes, state_filter='candidates', search=''):
    visible = []
    for node in nodes:
        base = node['state'].split('+')[0]
        healthy = node['eligible'] and base in ('IDLE', 'MIXED')
        if state_filter in ('candidates', 'healthy') and not healthy:
            continue
        if state_filter == 'unavailable' and node['eligible']:
            continue
        if state_filter in ('IDLE', 'MIXED', 'ALLOCATED') and base != state_filter:
            continue
        capacity = {}
        for model, total in node['capacity'].items():
            used = node['used'][model]
            if state_filter == 'candidates' and (used is None or used >= total):
                continue
            if search and search.lower() not in f'{node["name"]} {model} {node["state"]} {node["partitions"]} {node.get("reason", "")}'.lower():
                continue
            capacity[model] = total
        if capacity:
            visible.append({**node, 'capacity': capacity,
                            'used': {model: node['used'][model] for model in capacity}})
    return visible


def gpu_row_order(node, model, sort='preference'):
    used = node['used'][model]
    free = max(0, node['capacity'][model] - used) if used is not None else -1
    readiness = 0 if node['eligible'] and free > 0 else 1 if node['eligible'] else 2
    rank = GPU_PREFERENCE.get(model.lower(), 99)
    if sort == 'name':
        return (node['name'], model)
    if sort == 'free':
        return (readiness, -free, rank, node['name'], model)
    return (readiness, rank, -free, node['name'], model)


def request_groups(nodes, selected):
    """Group selected rows into independent, typed one-GPU requests."""
    groups = {}
    selected = set(selected)
    for node in nodes:
        for model in node['capacity']:
            if (node['name'], model) in selected:
                groups.setdefault(model, []).append(node['name'])
    return {model: sorted(set(names)) for model, names in sorted(groups.items(),
            key=lambda item: (GPU_PREFERENCE.get(item[0].lower(), 99), item[0]))}


def gpu_request(model, node=None):
    if model != 'untyped' and not re.fullmatch(r'[A-Za-z0-9_.-]+', model):
        raise Error('This GPU model cannot be copied as a Slurm GRES request.')
    lines = []
    if node:
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', node):
            raise Error('Invalid Slurm node name.')
        lines.extend(['#SBATCH --nodes=1', '#SBATCH --nodelist=' + node])
    lines.append('#SBATCH --gres=gpu:' + (model + ':' if model != 'untyped' else '') + '1')
    return '\n'.join(lines) + '\n'


def parse_queue(output):
    jobs = []
    for line in output.splitlines():
        bits = [part.strip() for part in line.strip().split('|')]
        if len(bits) == 8:
            job, name, state, elapsed, limit, reason, gpu, partition = bits
            jobs.append(dict(id=job, name=name, state=state, elapsed=elapsed, limit=limit,
                             reason=reason, gpu=gpu, partition=partition))
    return jobs


def parse_accounting(output):
    jobs = []
    for line in output.splitlines():
        b = line.strip().split('|')
        if len(b) >= 8 and re.fullmatch(r'\d+(?:_\d+)?', b[0]):
            job, name, state, elapsed, limit, nodes, resources, exitcode = b[:8]
            jobs.append(dict(id=job, name=name, state=state, elapsed=elapsed, limit=limit,
                             reason=nodes, gpu=resources, exit=exitcode, partition=''))
    return jobs


@contextlib.contextmanager
def project_lock(profile: Profile):
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = hashlib.sha256(f'{profile.host}:{profile.remote}'.encode()).hexdigest()[:20]
    with (STATE / f'{key}.lock').open('w') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Error('Another sync/submission is using this remote project.') from exc
        yield


class Backend:
    def __init__(self, profile: Profile):
        self.profile = profile.validate()
        directory = Path.home() / '.ssh' / 'hendrix-control'
        directory.mkdir(parents=True, mode=0o700, exist_ok=True)
        directory.chmod(0o700)
        self.options = ['-o', 'ControlMaster=auto', '-o', 'ControlPersist=15m',
                        '-o', f'ControlPath={directory}/%C', '-o', 'ConnectTimeout=8',
                        '-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=2']

    def ssh_argv(self, command=None, batch=True):
        args = ['ssh', *self.options]
        if batch:
            args += ['-o', 'BatchMode=yes']
        args += [self.profile.host]
        if command is not None:
            args += [command]
        return args

    def remote(self, command, timeout=20):
        try:
            result = subprocess.run(self.ssh_argv(command), text=True, capture_output=True,
                                    timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise Error('SSH timed out; data is stale. Connect explicitly before retrying.') from exc
        if result.returncode:
            raise Error((result.stderr or result.stdout or 'Remote command failed.').strip()[-3000:])
        return result.stdout

    def connect(self):
        # Reuse an existing session. Never start an unattended password prompt.
        if subprocess.run(['ssh', *self.options, '-O', 'check', self.profile.host],
                          capture_output=True).returncode == 0:
            return
        result = subprocess.run(['ssh', *self.options, '-fN', self.profile.host])
        if result.returncode:
            raise Error('SSH login failed. Check your VPN and account access.')

    def root_command(self):
        # Quote user-provided paths; only the initial ~/ prefix expands remotely.
        value = self.profile.remote.rstrip('/')
        expression = ('"$HOME"/' + shlex.quote(value[2:])) if value.startswith('~/') else shlex.quote(value)
        return f'root={expression}; '

    def remote_root(self):
        value = self.remote(self.root_command() + 'printf "%s\\n" "$root"').strip()
        if not value.startswith('/') or '\n' in value:
            raise Error('Remote home expansion returned an invalid path.')
        return value

    def nodes(self):
        return parse_nodes(self.remote('scontrol show nodes -d -o'))

    def jobs(self, history=False):
        command = ('set -e; squeue -h -u "$USER" -O '
                   '"JobID:0|,Name:0|,State:0|,TimeUsed:0|,TimeLimit:0|,ReasonList:0|,tres-per-node:0|,Partition:0"')
        if history:
            command += ('; printf "\\n__HENDRIX_HISTORY__\\n"; '
                        'sacct -X -n -P -u "$USER" --starttime now-2days '
                        '--format=JobID%64,JobName%128,State%64,Elapsed,Timelimit,NodeList%256,AllocTRES%512,ExitCode '
                        '|| printf "__HENDRIX_ACCOUNTING_UNAVAILABLE__\\n"')
        output = self.remote(command)
        current, _, past = output.partition('__HENDRIX_HISTORY__')
        self.accounting_warning = '__HENDRIX_ACCOUNTING_UNAVAILABLE__' in past
        jobs = {j['id']: j for j in parse_accounting(past)}
        jobs.update({j['id']: j for j in parse_queue(current)})
        return list(jobs.values())

    def history(self):
        path = STATE / 'history.json'
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text())
        except (ValueError, OSError) as exc:
            raise Error('Cannot read local job history; repair history.json before submitting.') from exc

    def record(self, record):
        # A separate lock protects history across different projects/processes.
        STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (STATE / 'history.lock').open('w') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            history = self.history()
            history.append(record)
            atomic_json(STATE / 'history.json', history)

    def matching_record(self, job):
        return next((r for r in reversed(self.history()) if r.get('job_id') == job
                     and r.get('host') == self.profile.host), None)

    def _sync(self, dry=False):
        local = Path(self.profile.local).expanduser().resolve()
        if not local.is_dir():
            raise Error(f'Local project does not exist: {local}')
        root = self.remote_root()
        dest = root + '/.hendrix/source'
        # Refuse symlink-managed roots; deletion is restricted to this marked source directory.
        if not dry:
            self.remote(self.root_command() + '''set -eu
mkdir -p -- "$root"
[ ! -L "$root/.hendrix" ] || { echo 'Refusing symlink .hendrix' >&2; exit 1; }
mkdir -p -- "$root/.hendrix"
[ ! -L "$root/.hendrix/source" ] || { echo 'Refusing symlink source directory' >&2; exit 1; }
if [ -d "$root/.hendrix/source" ] && [ ! -f "$root/.hendrix/managed-v1" ]; then
  echo 'Existing unmarked .hendrix/source; refusing to overwrite' >&2; exit 1
fi
mkdir -p -- "$root/.hendrix/source"
touch -- "$root/.hendrix/managed-v1"
''')
        args = ['rsync', '-az', '--itemize-changes', '--stats', '--delete-delay',
                '--safe-links', '--protect-args', '-e', shlex.join(['ssh', *self.options,
                '-o', 'BatchMode=yes'])]
        for exclude in dict.fromkeys([*self.profile.excludes, '.hendrix/', *self.profile.shared,
                                      self.profile.venv]):
            args += ['--exclude', exclude]
        if dry:
            args += ['--dry-run']
            exists = self.remote(f'if [ -d {shlex.quote(dest)} ]; then printf yes; fi').strip()
            if not exists:
                # Preview an initial upload against an empty local receiver; do not initialise remotely.
                with tempfile.TemporaryDirectory(prefix='hendrix-preview-') as empty:
                    local_args = args.copy()
                    at = local_args.index('-e')
                    del local_args[at:at + 2]
                    result = subprocess.run([*local_args, str(local) + '/', empty + '/'],
                                            capture_output=True, text=True, timeout=600)
                    if result.returncode:
                        raise Error(result.stderr.strip())
                    return 'Initial sync (remote source mirror does not yet exist):\n' + result.stdout, root
        args += [str(local) + '/', f'{self.profile.host}:{dest}/']
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=600)
        except subprocess.TimeoutExpired as exc:
            raise Error('Sync timed out; no job was submitted. Retry sync explicitly.') from exc
        if result.returncode:
            raise Error((result.stderr or result.stdout).strip()[-3000:])
        if not dry:
            self.record(dict(kind='sync', project=self.profile.name, host=self.profile.host,
                             at=dt.datetime.now(dt.timezone.utc).isoformat()))
        return result.stdout, root

    def sync(self, dry=False):
        with project_lock(self.profile):
            return self._sync(dry)[0]

    def unresolved(self):
        result = []
        for path in (STATE / 'submissions').glob('*.json'):
            record = json.loads(path.read_text())
            if record.get('host') == self.profile.host and record.get('project') == self.profile.name and record.get('status') in ('submitting', 'uncertain'):
                result.append((path, record))
        return result

    def reconcile(self):
        unresolved = self.unresolved()
        if not unresolved:
            return 'No uncertain submissions for this project.'
        output = self.remote('set -e; squeue -h -u "$USER" -o "%i|%k"; '
                             'sacct -X -n -P -u "$USER" --starttime now-2days '
                             '--format=JobID%64,Comment%128 || true')
        found = {}
        for line in output.splitlines():
            values = line.strip().split('|')
            if len(values) >= 2 and re.fullmatch(r'\d+(?:_\d+)?', values[0]):
                found[values[1]] = values[0]
        messages = []
        for path, record in unresolved:
            job = found.get('hendrix-' + record['token'])
            if job:
                record.update(job_id=job, status='submitted')
                atomic_json(path, record)
                self.record(record)
                messages.append(f'Recovered accepted job {job} for {record["token"]}.')
            else:
                messages.append(f'No match for {record["token"]}; absence is not proof of rejection. '
                                'After checking the queue/accounting, use hendrix resolve TOKEN --job-id ID '
                                'or --not-submitted. New submissions stay blocked.')
        return '\n'.join(messages)

    def resolve(self, token, job_id=None, not_submitted=False):
        if not re.fullmatch(r'[A-Za-z0-9-]+', token):
            raise Error('Invalid submission token.')
        path = STATE / 'submissions' / f'{token}.json'
        if not path.exists():
            raise Error('Unknown submission token.')
        record = json.loads(path.read_text())
        if record['host'] != self.profile.host or record['project'] != self.profile.name:
            raise Error('Select the project that owns this submission with --project.')
        if record['status'] not in ('uncertain', 'submitting'):
            raise Error('This submission is already resolved.')
        if job_id:
            if not re.fullmatch(r'\d+', job_id):
                raise Error('Expected a numeric batch job ID.')
            # Verify ownership and token rather than trusting an arbitrary pasted ID.
            f = fields(self.remote('scontrol show job -o ' + shlex.quote(job_id)))
            if f.get('Comment') != 'hendrix-' + token:
                raise Error('The live job does not have this submission token. Use Reconcile for completed jobs.')
            record.update(job_id=job_id, status='submitted')
        elif not_submitted:
            record['status'] = 'confirmed-not-submitted'
        else:
            raise Error('Provide --job-id ID or --not-submitted after checking the queue.')
        atomic_json(path, record)
        self.record(record)
        return 'Submission resolved: ' + record['status']

    def submit(self, preset: dict, resources: dict):
        unresolved = self.unresolved()
        if unresolved:
            raise UncertainSubmission('Resolve the previous uncertain submission before submitting again: '
                                      + ', '.join(r['token'] for _, r in unresolved))
        script = relative_path(preset['script'])
        if not (Path(self.profile.local).expanduser() / script).is_file():
            raise Error(f'Batch script is missing locally: {script}')
        validate_resources(resources)
        args = [str(a) for a in preset.get('args', [])]
        with project_lock(self.profile):
            self.history()  # Fail before contacting the scheduler if state is corrupt.
            _, root = self._sync()
            token = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:10]
            snapshot = f'{root}/.hendrix/snapshots/{token}'
            output = f'{root}/results/runs/hendrix-{token}'
            links = []
            for shared in [*self.profile.shared, self.profile.venv]:
                target = f'{root}/{shared}'
                destination = f'{snapshot}/{shared}'
                # The filtered source must not already contain shared-path entries.
                links.append(f'mkdir -p -- {shlex.quote(str(PurePosixPath(destination).parent))}; '
                             f'ln -s -- {shlex.quote(target)} {shlex.quote(destination)}')
            command = self.root_command() + 'set -eu; '
            command += (f'mkdir -p -- {shlex.quote(str(PurePosixPath(snapshot).parent))} '
                        f'{shlex.quote(output)}; [ ! -L {shlex.quote(str(PurePosixPath(snapshot).parent))} ]; '
                        f'mkdir -- {shlex.quote(snapshot)}; '
                        f'cp -a -- "$root/.hendrix/source/." {shlex.quote(snapshot + "/")}; ')
            command += '; '.join(links) + '; '
            command += f'test -f {shlex.quote(snapshot + "/" + script)}; '
            self.remote(command, timeout=120)
            manifest = dict(kind='job', status='prepared', project=self.profile.name,
                host=self.profile.host, snapshot=snapshot, token=token, output=output,
                script=script, args=args, resources=resources, at=dt.datetime.now(dt.timezone.utc).isoformat())
            manifest_path = STATE / 'submissions' / f'{token}.json'
            atomic_json(manifest_path, manifest)
            flags = ['sbatch', '--parsable', '--partition=' + resources['partition'],
                     '--gres=gpu:' + (resources['model'] + ':' if resources['model'] != 'any' else '') + str(resources['gpus']),
                     '--cpus-per-task=' + str(resources['cpus']), '--mem=' + resources['memory'],
                     '--time=' + resources['time'], '--output=' + output + '/slurm-%j.out',
                     '--error=' + output + '/slurm-%j.err', '--comment=hendrix-' + token]
            env = f'export MEANFLOW_VENV={shlex.quote(root + "/" + self.profile.venv)}; '
            # No automatic retry: timeout/connection loss may occur after Slurm accepted it.
            manifest['status'] = 'submitting'
            atomic_json(manifest_path, manifest)
            try:
                response = self.remote(f'set -eu; cd -- {shlex.quote(snapshot)}; ' + env +
                                       shlex.join([*flags, script, *args]), timeout=30).strip()
            except Error as exc:
                manifest['status'] = 'uncertain'
                atomic_json(manifest_path, manifest)
                self.record(manifest)
                raise UncertainSubmission(f'Submission failed or its response was lost. Do not retry until '
                    f'you check squeue / sacct for comment hendrix-{token}. Snapshot: {snapshot}. {exc}') from exc
            if not re.fullmatch(r'\d+(?:;[A-Za-z0-9_.-]+)?', response):
                manifest['status'] = 'uncertain'
                atomic_json(manifest_path, manifest)
                self.record(manifest)
                raise UncertainSubmission(f'Unexpected sbatch response; check jobs before retrying: {response}')
            manifest.update(job_id=response.split(';')[0], status='submitted')
            atomic_json(manifest_path, manifest)
            self.record(manifest)
            return manifest

    def log_path(self, job, stderr=False):
        if not re.fullmatch(r'\d+(?:_\d+)?', job):
            raise Error('Select a concrete job ID.')
        record = self.matching_record(job)
        if record:
            return f'{record["output"]}/slurm-{job}.{"err" if stderr else "out"}'
        f = fields(self.remote('scontrol show job -o ' + shlex.quote(job)))
        path = f.get('StdErr' if stderr else 'StdOut', '')
        if not path.startswith('/'):
            raise Error('No log path found; completed jobs outside the TUI may need a manual path.')
        return path

    def logs(self, job, stderr=False):
        path = self.log_path(job, stderr)
        return self.remote(f'if [ -f {shlex.quote(path)} ]; then tail -n 150 -- {shlex.quote(path)}; '
                           'else printf "Log has not been created yet.\\n"; fi')

    def cancel(self, job):
        if not re.fullmatch(r'\d+(?:_\d+)?', job):
            raise Error('Select a concrete job ID.')
        return self.remote('scancel ' + shlex.quote(job))

    def download(self, job):
        record = self.matching_record(job)
        if not record:
            raise Error('Result download needs a job submitted by the TUI.')
        source = record['output']
        if record['script'].endswith('/smoke.sbatch'):
            source_result = self.remote_root() + '/results/runs/smoke-' + job
        elif record['script'].endswith('/train.sbatch'):
            source_result = self.remote_root() + '/results/runs/train-' + job
        else:
            source_result = None
        destination = Path(self.profile.local).expanduser() / 'results/runs' / f'hendrix-{job}'
        destination.mkdir(parents=True, exist_ok=True)
        for remote, local in [(source, destination / 'logs'), *(([(source_result, destination / 'outputs')]) if source_result else [])]:
            local.mkdir(exist_ok=True)
            command = ['rsync', '-az', '--protect-args', '--safe-links', '-e',
                       shlex.join(['ssh', *self.options, '-o', 'BatchMode=yes']),
                       f'{self.profile.host}:{remote}/', str(local) + '/']
            result = subprocess.run(command, capture_output=True, text=True, timeout=600)
            if result.returncode:
                raise Error(result.stderr.strip()[-3000:])
        return str(destination)


def validate_resources(r):
    for key in ('partition', 'model'):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', str(r[key])) or str(r[key]).startswith('-'):
            raise Error(f'Invalid {key}. Use an exact Slurm name (or model any).')
    if not 1 <= int(r['gpus']) <= 8 or not 1 <= int(r['cpus']) <= 1024:
        raise Error('GPU count must be 1–8 and CPU count must be positive.')
    if not re.fullmatch(r'\d+[KMGTP]?', r['memory'], re.I) or int(re.match(r'\d+', r['memory'])[0]) < 1:
        raise Error('Host RAM should look like 32G.')
    if not re.fullmatch(r'(?:\d+-)?\d{1,3}:\d{2}:\d{2}', r['time']):
        raise Error('Time should look like 05:00:00 or 1-00:00:00.')
    parts = r['time'].split(':')
    if int(parts[-1]) > 59 or int(parts[-2]) > 59:
        raise Error('Invalid minutes or seconds in time limit.')
