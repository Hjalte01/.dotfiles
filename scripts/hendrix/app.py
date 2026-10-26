"""Textual frontend. Automatic startup connection, modest polling, and bounded logs."""
from __future__ import annotations

import asyncio
import datetime as dt
import os
import json
import shutil
import re
import subprocess
import time
from pathlib import Path

from rich.text import Text

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (Button, DataTable, Footer, Header, Input, Label, RichLog,
                             Select, Static, TabbedContent, TabPane, OptionList, SelectionList)

from dotfiles_theme import install as install_theme, color as theme_color

from . import core
from .core import (Backend, Error, Profile, load_profiles, save_profiles,
                   summarize, visible_gpu_nodes, gpu_row_order, GPU_PREFERENCE, free_total, request_groups, gpu_request, atomic_json)
from .cli import connect, edit_profiles, setup_ssh, vpn


# Stable column keys are shared by rendering, the chooser and saved preferences.
TABLE_COLUMNS = {
    'models': [('model', 'Model', 12), ('gpu', 'Free GPUs', 18), ('vram', 'VRAM/GPU', 12),
               ('cpu', 'CPU', 13), ('ram', 'Host RAM GiB', 16),
               ('healthy', 'Healthy free', 12), ('pending', 'Pending tasks', 16)],
    'nodes': [('node', 'Node', None), ('model', 'Model', 9), ('gpu', 'Free GPUs', 18),
              ('state', 'State', 9), ('cpu', 'CPU', 8), ('ram', 'RAM GiB', 14)],
    'jobs': [('id', 'Job', None), ('run', 'Run', None), ('state', 'State', None),
             ('elapsed', 'Elapsed', None), ('reason', 'Node / reason', None),
             ('project', 'Project', None), ('limit', 'Limit', None),
             ('gpu', 'GPU', None), ('exit', 'Exit', None)],
    'cluster-queue': [('id', 'Job / array', 27), ('gpu', 'GPU request', 27),
                      ('tasks', 'Tasks / cap', 16), ('reason', 'Reason (raw)', 27),
                      ('cpus', 'CPUs/job', 9), ('memory', 'Host RAM min', 16),
                      ('limit', 'Limit', 13), ('submitted', 'Submitted (local)', 22),
                      ('start', 'Scheduler start (local)', 22), ('partition', 'Partition', 22)],
}
TABLE_NAMES = {'models': 'GPU models', 'nodes': 'GPU nodes', 'jobs': 'Jobs',
               'cluster-queue': 'Cluster queue'}
REQUIRED_COLUMNS = {'models': {'model', 'gpu'}, 'nodes': {'node', 'model', 'gpu'},
                    'jobs': {'id', 'run', 'state'}, 'cluster-queue': {'id', 'gpu'}}
COMPACT_COLUMNS = {'models': {'model', 'gpu', 'vram'},
                   'nodes': {'node', 'model', 'gpu', 'state'},
                   'jobs': {'id', 'run', 'state', 'elapsed', 'reason'},
                   'cluster-queue': {'id', 'gpu', 'tasks', 'reason'}}


def load_columns():
    choices = {key: set(value) for key, value in COMPACT_COLUMNS.items()}
    try:
        saved = json.loads((core.CONFIG / 'ui.json').read_text())
        if isinstance(saved, dict):
            for table, columns in saved.items():
                if table in choices and isinstance(columns, list):
                    valid = {key for key, _, _ in TABLE_COLUMNS[table]}
                    choices[table] = {key for key in columns if isinstance(key, str)} & valid | REQUIRED_COLUMNS[table]
    except (OSError, ValueError):
        pass
    return choices


def availability_bar(free, total):
    """Slurm unallocated share, with exact counts and an explicit unknown state."""
    width = 8
    known = free is not None and total is not None and total > 0
    filled = round(width * min(1, max(0, free / total))) if known else 0
    result = Text('█' * filled, style=theme_color('green'))
    result.append(('─' * (width - filled)) if known else '?' * width, style=theme_color('muted'))
    result.append(' ' + free_total(free, total), style=theme_color('green') if known and free > 0 else theme_color('muted'))
    return result


class NavigationTable(DataTable):
    BINDINGS = [Binding('h', 'cursor_left', show=False), Binding('j', 'cursor_down', show=False),
                Binding('k', 'cursor_up', show=False), Binding('l', 'cursor_right', show=False),
                Binding('g', 'scroll_top', show=False), Binding('G', 'scroll_bottom', show=False),
                Binding('ctrl+d', 'page_down', show=False), Binding('ctrl+u', 'page_up', show=False)]


class NavigationLog(RichLog):
    BINDINGS = [Binding('j', 'scroll_down', show=False), Binding('k', 'scroll_up', show=False),
                Binding('h', 'scroll_left', show=False), Binding('l', 'scroll_right', show=False),
                Binding('g', 'scroll_home', show=False), Binding('G', 'scroll_end', show=False),
                Binding('ctrl+d', 'page_down', show=False), Binding('ctrl+u', 'page_up', show=False)]


class NavigationSelect(Select):
    BINDINGS = [Binding('j,k', 'show_overlay', show=False)]

    def __init__(self, *args, **kwargs):
        # Printable type-ahead would consume j/k before navigation bindings.
        kwargs['type_to_search'] = False
        super().__init__(*args, **kwargs)

    def on_mount(self):
        # Select's popup is a separate focusable OptionList. Bind there so its
        # parent Select does not reopen/reset the menu on the second j/k.
        overlay = self.query_one(OptionList)
        overlay._bindings.bind('j', 'cursor_down', show=False)
        overlay._bindings.bind('k', 'cursor_up', show=False)
        overlay._bindings.bind('h', 'cursor_up', show=False)
        overlay._bindings.bind('l', 'cursor_down', show=False)


class Confirm(ModalScreen[bool]):
    BINDINGS = [Binding('y,ctrl+enter', 'confirm', show=False), Binding('n', 'back', show=False)]

    def __init__(self, question):
        super().__init__()
        self.question = question

    def compose(self):
        with VerticalScroll(id='dialog'):
            yield Static(self.question, markup=False)
            with Horizontal():
                yield Button('Confirm', variant='primary', id='yes')
                yield Button('Back', id='no')

    def on_mount(self):
        self.query_one('#yes', Button).focus()
        self.call_after_refresh(self.query_one('#dialog', VerticalScroll).scroll_home, animate=False)

    def on_button_pressed(self, event):
        self.dismiss(event.button.id == 'yes')

    def action_confirm(self):
        self.dismiss(True)

    def action_back(self):
        self.dismiss(False)

    def key_escape(self):
        self.dismiss(False)


class Help(ModalScreen):
    def __init__(self, context=''):
        super().__init__()
        self.context = context

    def compose(self):
        with VerticalScroll(id='help-dialog'):
            yield Static('Hendrix · Help', classes='dialog-title')
            yield Static(
                'NAVIGATION\n'
                '1: GPU models · 2: GPU nodes · 3: Jobs · 4: Logs · 5: Projects · 6: Cluster queue\n'
                'hjkl: table arrows and menu navigation · Tab / Shift+Tab: next / previous control\n'
                'g/G: first/last table row · Ctrl+d/u: page down/up\n'
                'Alt+h/l: change tabs · /: search · Esc: leave search\n'
                'c: reconnect · r: refresh · C: choose table columns\n'
                'Shift+L: logs · q: quit · ?: this help\n\n'
                'GPU VIEW\n'
                'GPU bars show the free share; resource counts are free(total). For example, 4(6) means four free of six.\n'
                'GPU free counts come from Slurm allocations. CPU free = effective CPUs − CPUAlloc.\n'
                'RAM GiB is configured host RAM minus Slurm-allocated RAM, not GPU VRAM or OS FreeMem.\n'
                'Unknown counters are ?. CPU/RAM belong to the node and are shared by its GPUs;\n'
                'on a node with several GPU models, those CPU/RAM counts appear with each model.\n'
                'Summary totals follow the state filter and search. Unallocated does not guarantee\n'
                'immediate scheduling: permissions, reservations, CPU/RAM and queue priority still apply.\n\n'
                'IDLE: no jobs · MIXED: partly allocated · ALLOCATED: occupied by jobs.\n'
                'Slurm need not fill one node first: another job may need more CPUs/RAM,\n'
                'a different GPU, or resources limited by reservations and scheduling policy.\n'
                'DOWN/DRAIN/maintenance: unavailable for new jobs. Healthy + free hides these.\n'
                'Reasons shows the number of visible nodes with an explanation; it starts hidden.\n'
                'Click a column heading to sort; click again to reverse. = restores model preference.\n'
                'Default preference: H100, A100, L40S, A40, RTX, Titans. This is not a benchmark.\n'
                'C / Columns: choose optional columns per table; Compact/All presets are available.\n'
                'Choices are saved locally; CPU/RAM and queue details can be shown when needed.\n\n'
                'QUEUE AND COMPARISON\n'
                '6: visible pending demand by partition; default gpu, or all visible partitions.\n'
                'Compact arrays show pending task counts and concurrency caps without expanding tasks.\n'
                'Waiting = Resources/Priority. Blocked = dependencies, holds, array caps, future starts.\n'
                'Other scheduler reasons stay explicit; explanations preserve the raw Slurm reason.\n'
                'Any GPU demand is separate. Counts are visible demand, never jobs ahead of you.\n'
                'Click Pending tasks to sort; GPU sorts free capacity; = restores model preference.\n'
                'SELECTION AND COPY\n'
                'v: mark/unmark the focused node or model · Shift+V: clear marks.\n'
                'y: copy a one-GPU model request for the marked rows or focused row/model.\n'
                'Shift+Y: review the request; optionally pin ONE exact node.\n'
                'Mixed-model selections open a chooser: Slurm GRES types are not an OR-list.\n'
                'Marking several nodes does not request several GPUs or a multi-node job.\n'
                'A model request leaves node choice to Slurm. An exact-node request may wait longer.\n'
                'Copies are saved locally in ~/.local/state/hendrix/copied-request.json as well.\n'
                'Selected rows stay marked across filters; refreshed inventory removes vanished rows.\n\n'
                'CONNECTION\n'
                'hendrix tui connects automatically and loads GPU availability.\n'
                'Desktop Connect reuses the saved KUnet password for SSH after session/key checks.\n'
                'Save login password updates the VPN/SSH password; hendrix totp configures optional automatic VPN codes.\n'
                'Jobs poll every 30s, nodes/cluster queue every 60s; filters use cached data.\n'
                'Queue freshness and partial failures are shown; working data remains available.\n'
                'After a lost submission response, use Reconcile before attempting another job.\n'
                '\nOTHER SLURM WORKFLOWS (SSH / SCRIPTS)\n'
                'Batch: sbatch script.sbatch; pending/running jobs survive disconnect.\n'
                'Interactive: salloc, then srun --pty bash on allocated resources; keep session attached.\n'
                'Arrays: #SBATCH --array=0-9%2; use SLURM_ARRAY_TASK_ID; logs use %A_%a.\n'
                'Dependencies: sbatch --dependency=afterok:JOB script; future start: --begin=now+1hour.\n'
                'Holds: sbatch --hold, scontrol hold JOB; resume: scontrol release JOB.\n'
                'Monitoring: squeue, scontrol show job JOB; accounting: sacct, sstat for running steps.\n'
                'Cancel: TUI confirmation or scancel JOB; arrays: scancel ARRAY_TASK.\n'
                'Logs/results: TUI tail/download or SSH tail and rsync; use your script output paths.\n'
                'Modules/environments: module avail/load, project venv; configure inside batch scripts.\n'
                'Files/storage: SSH df/quota when available, scp/rsync for datasets and environments.\n'
                'Notebooks: request an interactive allocation, start Jupyter on loopback, SSH tunnel.\n'
                'Detailed examples and storage/tunnel guidance: ~/.dotfiles/docs/hendrix.md\n'
                + ('\nCURRENT CONTEXT\n' + self.context if self.context else ''), markup=False)
            yield Button('Close', id='close-help', variant='primary')

    def on_button_pressed(self, event):
        if event.button.id == 'close-help':
            self.dismiss()

    def key_escape(self):
        self.dismiss()


class CopyRequest(ModalScreen[tuple[str, str | None] | None]):
    def __init__(self, groups):
        super().__init__()
        self.groups = groups

    def compose(self):
        with Vertical(id='dialog'):
            yield Static('Copy Slurm request', classes='dialog-title')
            yield NavigationSelect([(model, model) for model in self.groups],
                                   value=next(iter(self.groups)), allow_blank=False, id='copy-model')
            yield Static('', id='copy-preview', markup=False)
            yield Static('One GPU of the chosen model; Slurm chooses the node.', classes='muted')
            with Horizontal(classes='actions'):
                yield Button('Copy model', id='copy-gpu', variant='primary')
                yield Button('Pin exact node', id='copy-node')
                yield Button('Back', id='copy-back')

    def on_mount(self):
        self.update_preview()

    def update_preview(self):
        model = self.query_one('#copy-model', Select).value
        if not isinstance(model, str):
            return
        self.query_one('#copy-preview', Static).update(
            gpu_request(model).strip() + '\n\nSelected rows: ' + ', '.join(self.groups[model]))
        pin = self.query_one('#copy-node', Button)
        pin.disabled = len(self.groups[model]) != 1
        pin.tooltip = 'Pinning requests this one exact node and may increase queue wait.'

    def on_select_changed(self, event):
        if event.select.id == 'copy-model' and self.query('#copy-preview'):
            self.update_preview()

    def on_button_pressed(self, event):
        if event.button.id == 'copy-back':
            self.dismiss(None)
        elif event.button.id in ('copy-gpu', 'copy-node'):
            model = self.query_one('#copy-model', Select).value
            node = self.groups[model][0] if event.button.id == 'copy-node' else None
            self.dismiss((model, node))

    def key_escape(self):
        self.dismiss(None)


def native_clipboard(text):
    command = None
    if os.environ.get('WAYLAND_DISPLAY') and shutil.which('wl-copy'):
        command = ['wl-copy', '--type', 'text/plain']
    elif os.environ.get('DISPLAY') and shutil.which('xclip'):
        command = ['xclip', '-selection', 'clipboard']
    if command is None:
        return False
    try:
        return subprocess.run(command, input=text, text=True, capture_output=True, timeout=3).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


class AddProject(ModalScreen[Profile | None]):
    def compose(self):
        with Vertical(id='dialog'):
            yield Label('Add a project (edit profiles for exclusions and presets)')
            for ident, title, value in [('name', 'Project name', ''), ('local', 'Absolute local root', ''),
                                        ('remote', 'Remote root', '~/projects/'), ('host', 'SSH alias', 'hendrix')]:
                yield Label(title)
                yield Input(value=value, id='add-' + ident)
            yield Static('', id='form-error', markup=False)
            with Horizontal():
                yield Button('Save', variant='primary', id='save')
                yield Button('Back', id='back')

    def on_button_pressed(self, event):
        if event.button.id == 'back':
            self.dismiss(None)
            return
        try:
            values = {key: self.query_one('#add-' + key, Input).value.strip()
                      for key in ('name', 'local', 'remote', 'host')}
            profile = Profile(**values).validate()
            scripts = Path(profile.local).expanduser() / 'scripts'
            if scripts.is_dir():
                profile.presets = [dict(name=p.stem, script=str(p.relative_to(Path(profile.local).expanduser())),
                                        args=[], time='00:30:00') for p in sorted(scripts.rglob('*.sbatch'))[:30]]
            self.dismiss(profile)
        except (Error, ValueError, OSError) as exc:
            self.query_one('#form-error', Static).update(str(exc))

    def key_escape(self):
        self.dismiss(None)


class ColumnChooser(ModalScreen[dict | None]):
    def __init__(self, choices, table):
        super().__init__()
        self.choices = {key: set(value) for key, value in choices.items()}
        self.table = table

    def compose(self):
        with VerticalScroll(id='dialog', classes='columns-dialog'):
            yield Static('Table columns', classes='dialog-title')
            yield NavigationSelect([(name, key) for key, name in TABLE_NAMES.items()],
                                   value=self.table, allow_blank=False, id='column-table')
            yield Static('Space toggles optional columns. Identity columns stay visible.', classes='muted')
            yield SelectionList(id='column-list')
            with Vertical(classes='column-buttons'):
                yield Button('Compact', id='column-compact')
                yield Button('All columns', id='column-all')
                yield Button('Save', id='column-save', variant='primary')
                yield Button('Back', id='column-back')

    def on_mount(self):
        self.fill_options()
        self.query_one('#column-list', SelectionList).focus()

    def fill_options(self):
        options = self.query_one('#column-list', SelectionList)
        options.clear_options()
        options.add_options([(label, key, key in self.choices[self.table])
                             for key, label, _ in TABLE_COLUMNS[self.table]
                             if key not in REQUIRED_COLUMNS[self.table]])

    def capture(self):
        self.choices[self.table] = set(self.query_one('#column-list', SelectionList).selected) | REQUIRED_COLUMNS[self.table]

    def on_select_changed(self, event):
        if event.select.id == 'column-table' and isinstance(event.value, str) and event.value != self.table:
            self.capture()
            self.table = event.value
            self.fill_options()

    def on_button_pressed(self, event):
        event.stop()
        if event.button.id == 'column-back':
            self.dismiss(None)
        elif event.button.id == 'column-save':
            self.capture()
            self.dismiss(self.choices)
        elif event.button.id in ('column-compact', 'column-all'):
            self.choices[self.table] = (set(COMPACT_COLUMNS[self.table]) if event.button.id == 'column-compact'
                                       else {key for key, _, _ in TABLE_COLUMNS[self.table]})
            self.fill_options()

    def key_escape(self):
        self.dismiss(None)


class HendrixApp(App):
    TITLE = 'Hendrix'
    SUB_TITLE = 'GPU availability · jobs'
    CSS = '''
    Screen { background: $background; overflow: hidden; }
    Header { background: $panel; height: 1; }
    #connection { height: 1; padding: 0 1; color: $foreground-muted; }
    #project-bar { height: 3; margin: 0 1; }
    #project { width: 1fr; }
    Button { margin-right: 1; min-width: 10; }
    #terminal { min-width: 7; }
    #help { min-width: 8; }
    TabbedContent { height: 1fr; min-height: 0; }
    TabPane { padding: 0 1; overflow-y: auto; }
    #gpu-controls { height: 3; margin: 0 0 1 0; }
    #node-filter { width: 1fr; margin-right: 1; }
    #state-filter { width: 30; }
    Select > SelectCurrent { border: round $border; background: $surface; }
    Select:focus > SelectCurrent { border: round $primary; }
    SelectOverlay { border: round $primary; background: $surface; max-height: 12; }
    #gpu-actions { height: 1; }
    #reasons { height: 1; min-width: 17; width: auto; border: none; padding: 0 1; background: $panel; color: $primary; }
    #gpu-view-status { height: 1; width: 1fr; color: $foreground-muted; text-align: right; }
    #models { height: 11; margin-bottom: 1; border: round $border; }
    #gpu-advice, #queue-status, #queue-summary, #queue-detail { height: auto; color: $foreground-muted; }
    #queue-controls { height: 3; }
    #queue-partition { width: 25; }
    #queue-filter { width: 1fr; }
    #cluster-queue { height: 1fr; min-height: 5; border: round $border; }
    #nodes { height: 1fr; min-height: 6; border: round $border; }
    DataTable > .datatable--header { background: $panel; color: $primary; text-style: bold; }
    DataTable > .datatable--cursor { background: $surface; color: $foreground; }
    #jobs-controls { height: 3; }
    #jobs-view { width: 28; }
    #jobs-limit-label { width: auto; padding: 1; }
    #jobs-limit { width: 8; }
    #jobs-summary { height: auto; color: $foreground-muted; }
    #jobs { height: 1fr; min-height: 6; border: round $border; }
    #project-details { height: auto; margin: 1 0; }
    .actions { height: auto; min-height: 3; margin: 1 0; }
    #sync-output, #job-log { height: 1fr; border: round $border; }
    #log-status { height: auto; color: $foreground-muted; }
    ModalScreen { align: center middle; background: #000000 65%; }
    #dialog, #help-dialog { width: 80; max-width: 95%; max-height: 95%; height: auto; border: thick $primary; padding: 1 2; background: $surface; }
    #help-dialog { height: 90%; }
    #dialog Static, #dialog Label, #help-dialog Static { height: auto; margin-bottom: 1; }
    #dialog Input, #dialog Select { margin-bottom: 1; }
    #dialog Horizontal { height: 3; }
    #dialog.columns-dialog { width: 76; padding: 0 1; }
    #dialog.columns-dialog Static, #dialog.columns-dialog Select { margin-bottom: 0; }
    #column-list { height: auto; max-height: 10; margin: 0; }
    #dialog .column-buttons { height: 2; layout: grid; grid-size: 2; grid-columns: 1fr 1fr; grid-rows: 1; }
    .column-buttons Button { width: 100%; height: 1; border: none; padding: 0 1; }
    .dialog-title { color: $primary; text-style: bold; }
    .muted { color: $foreground-muted; }
    '''
    BINDINGS = [('q', 'quit', 'Quit'), ('c', 'connect', 'Connect'), ('r', 'refresh', 'Refresh'),
                ('C', 'columns', 'Columns'),
                Binding('s', 'sync', 'Sync', show=False), Binding('p', 'preview', 'Preview', show=False),
                ('L', 'logs', 'Logs'), ('e', 'edit', 'Profiles'), ('t', 'terminal', 'SSH'),
                ('?', 'help', 'Help'), Binding('/', 'search', 'Search', show=False),
                Binding('v', 'mark', 'Mark', show=False), Binding('V', 'clear_marks', 'Clear marks', show=False),
                Binding('y', 'yank', 'Copy GPU', show=False), Binding('Y', 'review_copy', 'Review copy', show=False),
                Binding('R', 'reasons', 'Reasons', show=False), Binding('=', 'default_sort', 'Default sort', show=False),
                Binding('h,k', 'previous_control', 'Previous control', show=False),
                Binding('j,l', 'next_control', 'Next control', show=False),
                Binding('alt+h', 'previous_tab', 'Previous tab', show=False),
                Binding('alt+l', 'next_tab', 'Next tab', show=False),
                Binding('1', 'section(1)', 'Models', show=False),
                Binding('2', 'section(2)', 'Nodes', show=False),
                Binding('3', 'section(3)', 'Jobs', show=False),
                Binding('4', 'section(4)', 'Logs', show=False),
                Binding('5', 'section(5)', 'Projects', show=False),
                Binding('6', 'section(6)', 'Cluster queue', show=False)]

    def __init__(self, project=None):
        super().__init__()
        self.profiles = load_profiles()
        self.profile = next((p for p in self.profiles if p.name == project), self.profiles[0])
        self.backend = Backend(self.profile)
        self.startup_connected = False
        self.startup_error = None
        self.column_choices = load_columns()
        self.connected = False
        self.busy = False
        self.refreshing = False
        self.nodes = []
        self.jobs = []
        self.jobs_view = 'recent'
        self.jobs_limit = 3
        self.cluster_jobs = None
        self.queue_warning = ''
        self.data_errors = {}
        self.queue_partition = 'gpu'
        self.old_jobs = {}
        self.last_gpu = self.last_history = self.last_jobs = self.last_queue = 0
        self.last_gpu_at = self.last_queue_at = None
        self.marked_rows = set()
        self.sort_key = 'preference'
        self.sort_reverse = False
        self.show_reasons = False
        self.node_rows = {}
        self.connection_detail = 'Disconnected'
        self.log_job = None
        self.log_backend = None
        self.log_follow = False
        self.log_text = ''
        self.stderr = False
        self.last_log = 0

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static('Disconnected · c connect', id='connection', markup=False)
        with Horizontal(id='project-bar'):
            yield NavigationSelect([(p.name, p.name) for p in self.profiles], value=self.profile.name,
                         allow_blank=False, id='project')
            yield Button('Connect', id='connect', variant='primary')
            yield Button('SSH', id='terminal')
            yield Button('Columns', id='columns')
            yield Button('? Help', id='help')
        with TabbedContent():
            with TabPane('1/2 GPUs', id='gpu-tab'):
                with Horizontal(id='gpu-controls'):
                    yield Input(placeholder='/ Search model, node, state…', id='node-filter')
                    yield NavigationSelect([('Healthy + free GPUs', 'candidates'), ('Healthy nodes', 'healthy'),
                                            ('All nodes', 'all'), ('Idle nodes', 'IDLE'), ('Mixed nodes', 'MIXED'),
                                            ('Allocated nodes', 'ALLOCATED'), ('Unavailable nodes', 'unavailable')],
                                           value='candidates', allow_blank=False, id='state-filter')
                with Horizontal(id='gpu-actions'):
                    yield Button('Reasons off (0)', id='reasons')
                    yield Static('', id='gpu-view-status', markup=False)
                yield Static('', id='gpu-advice', markup=False)
                yield NavigationTable(id='models', cursor_type='row')
                yield NavigationTable(id='nodes', cursor_type='row')
            with TabPane('3/4 Jobs / Logs', id='jobs-tab'):
                with Horizontal(id='jobs-controls'):
                    yield NavigationSelect([('Active + recent finished', 'recent'), ('Active only', 'active'),
                                            ('Recent finished', 'finished'), ('Completed only', 'completed'),
                                            ('All jobs', 'all')],
                                           value=self.jobs_view, allow_blank=False, id='jobs-view')
                    yield Label('Recent finished (-1 = all):', id='jobs-limit-label')
                    yield Input(value=str(self.jobs_limit), type='integer', id='jobs-limit')
                yield Static('', id='jobs-summary', markup=False)
                yield NavigationTable(id='jobs', cursor_type='row')
                with Horizontal(classes='actions'):
                    yield Button('Logs', id='logs')
                    yield Button('Follow: off', id='follow')
                    yield Button('stderr', id='stderr')
                    yield Button('Download results', id='download')
                    yield Button('Cancel job', id='cancel', variant='error')
                yield Static('Select a job and open its logs. Tail is limited to the last 150 lines.', id='log-status', markup=False)
                yield NavigationLog(id='job-log', wrap=True, markup=False, max_lines=150)
            with TabPane('5 Projects', id='project-tab'):
                yield Static('', id='project-details', markup=False)
                with Horizontal(classes='actions'):
                    yield Button('Preview', id='preview')
                    yield Button('Sync', id='sync', variant='primary')
                with Horizontal(classes='actions'):
                    yield Button('Add project', id='add')
                    yield Button('Edit profiles', id='edit')
                    yield Button('Reconcile', id='reconcile')
                with Horizontal(classes='actions'):
                    yield Button('Save login password', id='password')
                    yield Button('Setup SSH key', id='setup-key')
                yield NavigationLog(id='sync-output', wrap=True, markup=False, max_lines=1000)
            with TabPane('6 · Cluster queue', id='queue-tab'):
                with Horizontal(id='queue-controls'):
                    yield NavigationSelect([('gpu', 'gpu'), ('All visible partitions', '*')],
                                           value='gpu', allow_blank=False, id='queue-partition')
                    yield Input(placeholder='/ Search job, model, reason…', id='queue-filter')
                yield Static('', id='queue-status', markup=False)
                yield Static('', id='queue-summary', markup=False)
                yield NavigationTable(id='cluster-queue', cursor_type='row')
                yield Static('', id='queue-detail', markup=False)
        yield Footer()

    def on_mount(self):
        install_theme(self)
        for ident, title in [('models', '1 · GPU models'), ('nodes', '2 · GPU nodes'),
                             ('jobs', '3 · Jobs'), ('job-log', '4 · Logs')]:
            self.query_one('#' + ident).border_title = title
        self.render_nodes()
        self.render_cluster_queue()
        self.render_jobs()
        self.show_profile()
        self.set_interval(5, self.tick)
        self.query_one('#models', DataTable).focus()
        if self.startup_connected:
            self.status('Connected · loading GPUs…')
            self.refresh_data(force=True)
        elif self.startup_error:
            self.status('Connection failed · c retry · ? details')
            self.connection_detail = self.startup_error
            self.output(self.startup_error)
            self.notify(self.startup_error, severity='error', timeout=10)

    def status(self, text):
        self.connection_detail = text
        widget = self.query_one('#connection', Static)
        widget.tooltip = text
        widget.update(text)

    def output(self, text):
        self.query_one('#sync-output', RichLog).write(text)

    def show_profile(self):
        last = next((r for r in reversed(self.backend.history()) if r.get('kind') == 'sync'
                     and r.get('project') == self.profile.name and r.get('host') == self.profile.host), None)
        self.query_one('#project-details', Static).update(
            f'{self.profile.name}\n{self.profile.local}\n{self.profile.host}:{self.profile.remote}\n'
            f'Last sync: {last["at"] if last else "never"}')

    def on_select_changed(self, event):
        if event.select.id == 'jobs-view' and isinstance(event.value, str):
            self.jobs_view = event.value
            if self.is_mounted:
                self.render_jobs()
            return
        if event.select.id == 'queue-partition' and isinstance(event.value, str):
            self.queue_partition = event.value
            if self.is_mounted and self.query('#cluster-queue'):
                self.render_cluster_queue()
                self.render_nodes()
            return
        if event.select.id == 'state-filter':
            if self.is_mounted and self.query('#nodes'):
                self.render_nodes()
            return
        if event.select.id != 'project' or not isinstance(event.value, str):
            return
        if self.busy:
            event.select.value = self.profile.name
            return
        new = next(p for p in self.profiles if p.name == event.value)
        if new.name == self.profile.name:
            return
        self.connected = False
        self.profile, self.backend = new, Backend(new)
        self.nodes, self.jobs, self.old_jobs = [], [], {}
        self.cluster_jobs, self.queue_warning, self.data_errors = None, '', {}
        self.marked_rows.clear()
        self.last_gpu = self.last_history = self.last_jobs = self.last_queue = 0
        self.last_gpu_at = self.last_queue_at = None
        self.log_job, self.log_follow = None, False
        self.query_one('#follow', Button).label = 'Follow: off'
        for ident in ('models', 'nodes', 'jobs'):
            self.query_one('#' + ident, DataTable).clear()
        self.query_one('#job-log', RichLog).clear()
        self.status('Project changed · c connect / r refresh')
        self.render_nodes()
        self.render_cluster_queue()
        self.show_profile()

    def on_input_changed(self, event):
        if event.input.id == 'jobs-limit':
            if re.fullmatch(r'-1|\d+', event.value):
                self.jobs_limit = int(event.value)
                if self.is_mounted:
                    self.render_jobs()
            return
        if event.input.id == 'node-filter':
            self.render_nodes()
        elif event.input.id == 'queue-filter':
            self.render_cluster_queue()

    def on_data_table_row_highlighted(self, event):
        if event.data_table.id == 'cluster-queue' and self.is_mounted:
            self.show_queue_detail()
        elif event.data_table.id == 'jobs' and self.is_mounted and self.log_job:
            job = str(event.row_key.value)
            if job == self.selected_job() and job != self.log_job:
                self.action_logs()

    def on_data_table_row_selected(self, event):
        if event.data_table.id == 'jobs':
            self.action_logs()

    def table_row_key(self, table):
        if not table.row_count:
            return None
        return str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)

    def header_label(self, key, title):
        if key == self.sort_key:
            return title + (' ↓' if self.sort_reverse else ' ↑')
        return title

    def sort_value(self, node, model):
        free = node['capacity'][model] - node['used'][model] if node['used'][model] is not None else None
        key = self.sort_key
        if key == 'preference':
            return gpu_row_order(node, model)
        if key == 'pending':
            demand = core.pending_demand(self.cluster_jobs or [], self.queue_partition).get(model)
            unknown = self.cluster_jobs is None or bool(demand and demand['unknown'])
            value = demand['tasks'] if demand else 0
            return (unknown, -value if self.sort_reverse else value, model, node['name'])
        if key in ('cpu', 'ram', 'gpu'):
            value = free if key == 'gpu' else node.get(key + '_free')
            # Unknown values stay last, irrespective of sort direction.
            return (value is None, (-value if self.sort_reverse else value) if value is not None else 0,
                    model, node['name'])
        value = model.lower() if key == 'model' else node['name'] if key == 'node' else node['state']
        return (value, node['name'], model)

    def resource_text(self, free, total, *, gib=False):
        style = theme_color("green") if free is not None and free > 0 else theme_color("yellow") if free is None else theme_color("muted")
        return Text(free_total(free, total, gib=gib), style=style)

    def add_table_columns(self, table, *, node_width=None):
        keys = []
        for key, label, width in TABLE_COLUMNS[table.id]:
            if key in self.column_choices[table.id]:
                if table.id == 'nodes' and key == 'node':
                    width = node_width
                title = self.header_label(key, label) if table.id in ('models', 'nodes') else label
                table.add_column(title, key=key, width=width)
                keys.append(key)
        return keys

    @work(group='columns', exclusive=True)
    async def action_columns(self):
        if isinstance(self.screen, ModalScreen):
            return
        active = self.query_one(TabbedContent).active
        table = self.focused.id if isinstance(self.focused, DataTable) else {
            'gpu-tab': 'models', 'jobs-tab': 'jobs', 'queue-tab': 'cluster-queue'}.get(active, 'models')
        choices = await self.push_screen_wait(ColumnChooser(self.column_choices, table))
        if choices is None:
            return
        try:
            atomic_json(core.CONFIG / 'ui.json', {key: sorted(value) for key, value in choices.items()})
        except OSError as exc:
            self.notify(f'Could not save columns: {exc}', severity='error')
            return
        self.column_choices = choices
        self.render_nodes()
        self.render_jobs()
        self.render_cluster_queue()

    def render_nodes(self):
        table = self.query_one('#nodes', DataTable)
        previous = self.table_row_key(table)
        horizontal = table.scroll_x
        models = self.query_one('#models', DataTable)
        previous_model = self.table_row_key(models)
        valid = {(n['name'], m) for n in self.nodes for m in n['capacity']}
        self.marked_rows.intersection_update(valid)
        nodes = visible_gpu_nodes(self.nodes, self.query_one('#state-filter', Select).value,
                                  self.query_one('#node-filter', Input).value)
        rows = sorted(((n, m) for n in nodes for m in n['capacity']), key=lambda pair: self.sort_value(*pair),
                      reverse=self.sort_reverse and self.sort_key in ('node', 'model', 'state'))
        reasons = len({n['name'] for n in nodes if n.get('reason')})
        reason_button = self.query_one('#reasons', Button)
        reason_button.label = f'Reasons {"on" if self.show_reasons else "off"} ({reasons})'
        reason_button.disabled = not reasons
        table.clear(columns=True)
        display_names = {n['name']: n['name'].removeprefix('hendrix') if self.size.width < 110 else n['name']
                         for n in nodes}
        # Reserve the trailing marker space even when nothing is marked, so
        # selection does not move the following columns.
        node_width = max(len(self.header_label('node', 'Node')),
                         max((len(name) for name in display_names.values()), default=0)) + 2
        node_columns = self.add_table_columns(table, node_width=node_width)
        if self.show_reasons and reasons:
            table.add_column('Unavailable reason', key='reason', width=36)
        self.node_rows = {}
        for index, (n, model) in enumerate(rows):
            row_key = n['name'] + ':' + model
            self.node_rows[row_key] = (n['name'], model)
            marked = (n['name'], model) in self.marked_rows
            name = display_names[n['name']]
            free = max(0, n['capacity'][model] - n['used'][model]) if n['used'][model] is not None else None
            state_style = theme_color("red") if not n['eligible'] else theme_color("green") if n['state'] == 'IDLE' else theme_color("yellow")
            values = {'node': Text(name + (' ●' if marked else ''),
                                   style=('bold ' + theme_color('accent')) if marked else theme_color('text')),
                      'model': model, 'gpu': availability_bar(free, n['capacity'][model]),
                      'cpu': self.resource_text(n.get('cpu_free'), n.get('cpu_total')),
                      'ram': self.resource_text(n.get('ram_free'), n.get('ram_total'), gib=True),
                      'state': Text(n['state'], style=state_style, overflow='ellipsis', no_wrap=True)}
            cells = [values[key] for key in node_columns]
            if self.show_reasons and reasons:
                cells.append(n.get('reason', ''))
            table.add_row(*cells, key=row_key)
            if row_key == previous:
                table.move_cursor(row=index, scroll=False)
        table.scroll_to(x=horizontal, animate=False)
        table.border_title = '2 · GPU nodes · free(total)'
        table.border_subtitle = 'v mark · y copy · C columns'
        models.clear(columns=True)
        model_columns = self.add_table_columns(models)
        totals = summarize(nodes)
        demand = core.pending_demand(self.cluster_jobs, self.queue_partition) if self.cluster_jobs is not None else None
        if self.sort_key == 'preference':
            totals.sort(key=lambda r: (GPU_PREFERENCE.get(r['model'].lower(), 99), r['model']))
        elif self.sort_key in ('gpu', 'cpu', 'ram'):
            field = 'unallocated' if self.sort_key == 'gpu' else self.sort_key + '_free'
            flag = 'unknown' if self.sort_key == 'gpu' else field + '_unknown'
            totals.sort(key=lambda r: (r[flag], -r[field] if self.sort_reverse else r[field], r['model']))
        elif self.sort_key == 'pending':
            def pending_sort(row):
                entry = demand.get(row['model']) if demand is not None else None
                value = entry['tasks'] if entry else 0
                return (demand is None or bool(entry and entry['unknown']),
                        -value if self.sort_reverse else value, row['model'])
            totals.sort(key=pending_sort)
        else:
            totals.sort(key=lambda r: r['model'], reverse=self.sort_reverse if self.sort_key == 'model' else False)
        for index, row in enumerate(totals):
            gpu = None if row['unknown'] else row['unallocated']
            cpu_free = None if row['cpu_free_unknown'] else row['cpu_free']
            cpu_total = None if row['cpu_total_unknown'] else row['cpu_total']
            ram_free = None if row['ram_free_unknown'] else row['ram_free']
            ram_total = None if row['ram_total_unknown'] else row['ram_total']
            marked = any(model == row['model'] for _, model in self.marked_rows)
            values = {'model': Text(row['model'] + (' ●' if marked else ''), style='bold ' + theme_color('accent')),
                      'gpu': availability_bar(gpu, row['total']),
                      'cpu': self.resource_text(cpu_free, cpu_total),
                      'ram': self.resource_text(ram_free, ram_total, gib=True),
                      'vram': core.gpu_metadata(row['model'])['vram'],
                      'healthy': '?' if row['usable_unknown'] else str(row['usable']),
                      'pending': '?' if demand is None or demand.get(row['model'], {}).get('unknown')
                                 else str(demand.get(row['model'], {}).get('tasks', 0))}
            models.add_row(*(values[key] for key in model_columns), key=row['model'])
            if row['model'] == previous_model:
                models.move_cursor(row=index, scroll=False)
        models.styles.height = min(12, max(4, len(totals) + 3))
        models.border_title = '1 · GPU models · free(total)'
        models.border_subtitle = 'v mark · y copy · Click heading to sort'
        total = sum(len(n['capacity']) for n in self.nodes)
        self.query_one('#gpu-view-status', Static).update(
            f'{len(rows)}/{total} rows · {len(self.marked_rows)} marked · '
            + ('model preference' if self.sort_key == 'preference' else self.sort_key + (' ↓' if self.sort_reverse else ' ↑')))
        self.query_one('#gpu-advice', Static).update(
            f'Inventory: {core.display_time(self.last_gpu_at)} · bars = free / total GPUs · Slurm allocations')

    def on_data_table_header_selected(self, event):
        if event.data_table.id not in ('models', 'nodes'):
            return
        key = str(event.column_key.value)
        if key not in ('node', 'model', 'gpu', 'cpu', 'ram', 'state', 'pending'):
            return
        if self.sort_key == key:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_key = key
            self.sort_reverse = key in ('gpu', 'cpu', 'ram')
        self.render_nodes()

    def action_default_sort(self):
        self.sort_key, self.sort_reverse = 'preference', False
        self.render_nodes()

    def action_reasons(self):
        self.show_reasons = not self.show_reasons
        self.render_nodes()

    def action_search(self):
        if isinstance(self.screen, ModalScreen):
            return
        if self.query_one(TabbedContent).active == 'queue-tab':
            self.query_one('#queue-filter', Input).focus()
        else:
            self.query_one(TabbedContent).active = 'gpu-tab'
            self.query_one('#node-filter', Input).focus()

    def key_escape(self):
        if isinstance(self.screen, ModalScreen):
            return
        if self.focused is self.query_one('#node-filter', Input):
            self.query_one('#nodes', DataTable).focus()
        elif self.focused is self.query_one('#queue-filter', Input):
            self.query_one('#cluster-queue', DataTable).focus()
        elif isinstance(self.focused, Input):
            self.screen.focus_next()

    def action_section(self, section):
        if isinstance(self.screen, ModalScreen):
            return
        pane, target = {1: ('gpu-tab', 'models'), 2: ('gpu-tab', 'nodes'),
                        3: ('jobs-tab', 'jobs'), 4: ('jobs-tab', 'job-log'),
                        5: ('project-tab', 'sync'), 6: ('queue-tab', 'cluster-queue')}[section]
        self.query_one(TabbedContent).active = pane
        self.query_one('#' + target).focus()

    def action_help(self):
        context = self.connection_detail
        key = self.table_row_key(self.query_one('#nodes', DataTable))
        if key in self.node_rows:
            name, model = self.node_rows[key]
            node = next(n for n in self.nodes if n['name'] == name)
            context += f'\nNode: {name} · GPU: {model} · partitions: {node["partitions"]}'
            if node.get('reason'):
                context += '\nReason: ' + node['reason']
        self.push_screen(Help(context))

    def action_mark(self):
        models = self.query_one('#models', DataTable)
        if self.focused is models:
            model = self.table_row_key(models)
            rows = {(n['name'], model) for n in self.nodes if model in n['capacity']}
            if rows and rows <= self.marked_rows:
                self.marked_rows.difference_update(rows)
            else:
                self.marked_rows.update(rows)
            self.render_nodes()
            return
        table = self.query_one('#nodes', DataTable)
        if self.focused is not table:
            self.notify('Focus a node row to mark it.')
            return
        row = self.node_rows.get(self.table_row_key(table))
        if row is None:
            return
        if row in self.marked_rows:
            self.marked_rows.remove(row)
        else:
            self.marked_rows.add(row)
        self.render_nodes()

    def action_clear_marks(self):
        self.marked_rows.clear()
        self.render_nodes()

    def copy_groups(self):
        if self.marked_rows:
            return request_groups(self.nodes, self.marked_rows)
        focused = self.focused
        if isinstance(focused, DataTable) and focused.id == 'models':
            model = self.table_row_key(focused)
            return request_groups(self.nodes, {(n['name'], model) for n in self.nodes if model in n['capacity']})
        row = self.node_rows.get(self.table_row_key(self.query_one('#nodes', DataTable)))
        return request_groups(self.nodes, [row] if row else [])

    @work(group='copy', exclusive=False)
    async def copy_request(self, review=False):
        if isinstance(self.screen, ModalScreen):
            return
        groups = self.copy_groups()
        if not groups:
            self.notify('Select a node or model first.')
            return
        if review or len(groups) > 1:
            selection = await self.push_screen_wait(CopyRequest(groups))
            if selection is None:
                return
            model, node = selection
        else:
            model, node = next(iter(groups)), None
        try:
            text = gpu_request(model, node)
            atomic_json(core.STATE / 'copied-request.json', dict(text=text, model=model, node=node,
                        inspected_nodes=groups[model], at=dt.datetime.now(dt.timezone.utc).isoformat()))
            native = await asyncio.to_thread(native_clipboard, text)
            if not native:
                self.copy_to_clipboard(text)  # OSC52 for terminal / remote use.
            self.notify('Copied ' + ('exact node request' if node else text.strip().removeprefix('#SBATCH --gres=')
                                    + ' · Slurm chooses the node'))
        except (Error, OSError) as exc:
            self.notify(str(exc), severity='error')

    def action_yank(self):
        self.copy_request()

    def action_review_copy(self):
        self.copy_request(review=True)

    def on_resize(self):
        if self.is_mounted and self.query('#nodes'):
            # Resize is delivered before the App's layout/size property updates.
            self.call_after_refresh(self.render_nodes)

    def action_previous_control(self):
        if isinstance(self.focused, OptionList):
            self.focused.action_cursor_up()
        else:
            self.screen.focus_previous()

    def action_next_control(self):
        if isinstance(self.focused, OptionList):
            self.focused.action_cursor_down()
        else:
            self.screen.focus_next()

    def change_tab(self, direction):
        if isinstance(self.screen, ModalScreen):
            return
        tabs = self.query_one(TabbedContent)
        panes = ['gpu-tab', 'jobs-tab', 'project-tab', 'queue-tab']
        tabs.active = panes[(panes.index(tabs.active) + direction) % len(panes)]
        target = {'gpu-tab': '#nodes', 'project-tab': '#sync', 'jobs-tab': '#jobs', 'queue-tab': '#cluster-queue'}[tabs.active]
        self.query_one(target).focus()

    def action_previous_tab(self):
        self.change_tab(-1)

    def action_next_tab(self):
        self.change_tab(1)

    def render_jobs(self):
        table = self.query_one('#jobs', DataTable)
        selected = self.selected_job()
        horizontal = table.scroll_x
        table.clear(columns=True)
        columns = self.add_table_columns(table)
        records = {r.get('job_id'): r for r in self.backend.history() if r.get('host') == self.profile.host}
        visible = core.visible_jobs(self.jobs, self.jobs_view, self.jobs_limit)
        for job in visible:
            record = records.get(job['id'], {})
            run_name = record.get('run_name') or record.get('preset_name')
            if not run_name and record:
                profile = next((p for p in self.profiles if p.name == record.get('project')), None)
                preset = next((p for p in profile.presets if p['script'] == record.get('script')
                               and p.get('args', []) == record.get('args', [])), None) if profile else None
                run_name = preset['name'] if preset else job['name']
            values = dict(job, project=record.get('project', '—'), run=run_name or job['name'],
                          gpu=core.compact_job_gpu(job['gpu']), exit=job.get('exit', ''))
            table.add_row(*(values[key] for key in columns), key=job['id'])
        if selected:
            for index, job in enumerate(visible):
                if job['id'] == selected:
                    table.move_cursor(row=index, scroll=False)
                    break
        self.call_after_refresh(table.scroll_to, x=horizontal, animate=False)
        active = sum(core.job_is_active(job) for job in visible)
        self.query_one('#jobs-summary', Static).update(
            f'{active} active · {len(visible) - active} finished shown · {len(self.jobs) - len(visible)} hidden'
            ' · Recent finished includes failures; All jobs shows loaded history.')

    def queue_freshness(self):
        text = 'Queue updated ' + core.display_time(self.last_queue_at) if self.last_queue_at else 'Queue not loaded'
        if self.last_queue_at:
            age = max(0, int((dt.datetime.now().astimezone() - self.last_queue_at).total_seconds()))
            text += f' ({age}s ago)'
        if 'queue' in self.data_errors:
            text += ' · stale: ' + self.data_errors['queue']
        if self.queue_warning:
            text += ' · partial: ' + self.queue_warning
        return text

    def render_cluster_queue(self):
        table = self.query_one('#cluster-queue', DataTable)
        previous, horizontal = self.table_row_key(table), table.scroll_x
        table.clear(columns=True)
        columns = self.add_table_columns(table)
        search = self.query_one('#queue-filter', Input).value.lower()
        visible = [j for j in self.cluster_jobs or [] if core.in_partition(j, self.queue_partition)]
        rows = [j for j in visible if not search or search in ' '.join(
            str(j[key]) for key in ('id', 'gpu', 'reason', 'explanation', 'partition', 'category')).lower()]
        rows.sort(key=lambda j: (j['submitted'] is None, j['submitted'] or dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc), j['id']))
        for index, job in enumerate(rows):
            tasks = str(job['tasks']) if job['tasks'] is not None else '?'
            cap = core.cap_text(job)
            values = dict(job, tasks=f'{tasks} / {cap}', submitted=core.display_time(job['submitted']),
                          start=core.display_time(job['start']))
            table.add_row(*(values[key] for key in columns), key=job['id'])
            if job['id'] == previous:
                table.move_cursor(row=index, scroll=False)
        table.scroll_to(x=horizontal, animate=False)
        table.border_title = '6 · Cluster queue · visible pending tasks'
        table.border_subtitle = 'j/k rows · h/l columns · / search · r refresh'
        self.update_queue_status(len(visible))
        demand = core.pending_demand(visible, '*')
        def name(model):
            return 'Any GPU' if model == 'any' else 'No GPU reported' if model == 'none' else model
        summary = ' · '.join(f'{name(model)}: {core.demand_text(row)}' for model, row in sorted(demand.items()))
        self.query_one('#queue-summary', Static).update('Visible pending demand: ' +
            (summary or ('none' if self.cluster_jobs is not None else 'unavailable')))
        self.show_queue_detail()

    def show_queue_detail(self):
        key = self.table_row_key(self.query_one('#cluster-queue', DataTable))
        job = next((j for j in self.cluster_jobs or [] if j['id'] == key), None)
        self.query_one('#queue-detail', Static).update(
            f"{job['id']} · {job['gpu']} · {job['tasks'] if job['tasks'] is not None else '?'} tasks · cap {core.cap_text(job)}\n"
            f"{job['explanation']} [{job['reason']}] · {job['cpus']} CPUs/job · {job['memory']} host RAM · limit {job['limit']}\n"
            f"Submitted {core.display_time(job['submitted'])} · scheduler start {core.display_time(job['start'])}"
            if job else 'Waiting = resources/priority. Blocked = dependencies, holds, array caps or future starts. Other reasons stay explicit.')

    def update_queue_status(self, visible=None):
        if visible is None:
            visible = sum(core.in_partition(j, self.queue_partition) for j in self.cluster_jobs or [])
        shown = self.query_one('#cluster-queue', DataTable).row_count
        self.query_one('#queue-status', Static).update(self.queue_freshness() +
            f'\n{shown}/{visible} pending records · counts describe visible demand, not queue position')

    def update_queue_partitions(self):
        partitions = {'gpu', self.queue_partition}
        for row in [*self.nodes, *(self.cluster_jobs or [])]:
            partitions.update(row.get('partitions', row.get('partition', '')).split(','))
        partitions -= {'', '?', '*'}
        select = self.query_one('#queue-partition', Select)
        select.set_options([(p, p) for p in sorted(partitions)] + [('All visible partitions', '*')])
        select.value = self.queue_partition

    def selected_job(self):
        table = self.query_one('#jobs', DataTable)
        if not table.row_count:
            return None
        return str(table.get_row_at(table.cursor_row)[0])

    def backend_for_job(self, job):
        record = self.backend.matching_record(job)
        if record:
            profile = next((p for p in self.profiles if p.name == record['project'] and p.host == record['host']), None)
            if profile is None:
                raise Error('This job belongs to a removed project profile; restore that profile to download results.')
            return Backend(profile)
        return self.backend

    def on_button_pressed(self, event):
        action = {'setup-key': 'setup_key'}.get(event.button.id, event.button.id)
        method = getattr(self, 'action_' + action, None)
        if method:
            method()

    def tick(self):
        now = time.monotonic()
        if self.connected and not self.busy and not self.refreshing and now - self.last_jobs >= 30:
            self.refresh_data()
        if self.connected and not self.busy and self.log_follow and self.log_job and now - self.last_log >= 10:
            self.read_logs()
        if self.is_mounted and not isinstance(self.screen, ModalScreen) and self.query('#queue-status'):
            self.update_queue_status()

    @work(group='refresh', exclusive=False)
    async def refresh_data(self, force=False):
        if self.busy or self.refreshing:
            return
        self.refreshing = True
        backend = self.backend
        try:
            now = time.monotonic()
            history = force or now - self.last_history >= 60
            queries = {'jobs': asyncio.to_thread(backend.jobs, history)}
            if force or now - self.last_gpu >= 60:
                queries['inventory'] = asyncio.to_thread(backend.nodes)
                self.last_gpu = now
            if force or now - self.last_queue >= 60:
                queries['queue'] = asyncio.to_thread(backend.cluster_queue)
                self.last_queue = now
            results = dict(zip(queries, await asyncio.gather(*queries.values(), return_exceptions=True)))
            if backend is not self.backend:
                return
            for name, result in results.items():
                if isinstance(result, Exception):
                    self.data_errors[name] = str(result)
                else:
                    self.data_errors.pop(name, None)
            jobs = results['jobs']
            if not isinstance(jobs, Exception):
                if history:
                    self.old_jobs = {j['id']: j for j in jobs if not core.job_is_active(j)}
                    self.last_history = now
                combined = dict(self.old_jobs)
                current_ids = {j['id'] for j in jobs}
                for previous in self.jobs:
                    if previous['id'] not in current_ids and previous['id'] not in combined:
                        combined[previous['id']] = {**previous, 'state': 'AWAITING_ACCOUNTING'}
                combined.update({j['id']: j for j in jobs})
                self.jobs = list(combined.values())
                self.render_jobs()
            self.last_jobs = now
            if 'inventory' in results and not isinstance(results['inventory'], Exception):
                self.nodes = results['inventory']
                self.last_gpu_at = dt.datetime.now().astimezone()
            if 'queue' in results and not isinstance(results['queue'], Exception):
                self.cluster_jobs, self.queue_warning = results['queue']
                self.last_queue_at = dt.datetime.now().astimezone()
            self.update_queue_partitions()
            self.render_cluster_queue()
            self.render_nodes()
            self.connected = any(not isinstance(r, Exception) for r in results.values())
            if not self.connected:
                self.log_follow = False
                self.query_one('#follow', Button).label = 'Follow: off'
            message = (f'{self.profile.host} · updated {time.strftime("%H:%M:%S")}' if self.connected else
                       'Disconnected · c reconnect / r retry')
            if self.data_errors:
                message += ' · stale: ' + ', '.join(self.data_errors)
            if getattr(backend, 'accounting_warning', False):
                message += ' · accounting unavailable'
            self.status(message)
            self.connection_detail += '\n' + '\n'.join(f'{key}: {value}' for key, value in self.data_errors.items())
        except (Error, OSError, ValueError, TypeError) as exc:
            if backend is self.backend:
                self.status('Refresh failed: ' + str(exc))
                self.notify(str(exc), severity='error', timeout=10)
        finally:
            self.refreshing = False

    def action_refresh(self):
        self.refresh_data(force=True)

    @work(group='operation', exclusive=False)
    async def foreground(self, action):
        if self.busy or self.refreshing:
            self.notify('Wait for the current operation to finish.')
            return
        self.busy = True
        connection_ready = False
        failure = None
        cancelled = False
        try:
            with self.suspend():
                # Textual's suspend context resumes the terminal only after a
                # normal exit. Keep failures inside it, then report after resume.
                try:
                    if action in ('connect', 'terminal', 'setup-key'):
                        connect(self.backend)
                        connection_ready = True
                    if action == 'terminal':
                        subprocess.run(self.backend.ssh_argv(batch=False))
                    elif action == 'password':
                        vpn('password', ['set'])
                    elif action == 'setup-key':
                        setup_ssh(self.backend)
                    elif action == 'edit':
                        edit_profiles()
                except KeyboardInterrupt:
                    cancelled = True
                except Exception as exc:
                    failure = exc
            if cancelled:
                self.output(f'{action}: cancelled')
                self.notify(f'{action}: cancelled', severity='warning')
            elif failure is not None:
                self.output(str(failure))
                self.notify(str(failure), severity='error', timeout=10)
            elif action == 'edit':
                self.profiles = load_profiles()
                self.profile = next((p for p in self.profiles if p.name == self.profile.name), self.profiles[0])
                self.backend = Backend(self.profile)
                select = self.query_one('#project', Select)
                select.set_options([(p.name, p.name) for p in self.profiles])
                select.value = self.profile.name
                self.show_profile()
            if not cancelled and failure is None:
                self.output(f'{action}: completed')
        except (Error, OSError, ValueError, subprocess.SubprocessError) as exc:
            self.output(str(exc))
            self.notify(str(exc), severity='error', timeout=10)
        finally:
            self.busy = False
        if connection_ready:
            self.refresh_data(force=True)

    def action_connect(self):
        self.foreground('connect')

    def action_terminal(self):
        self.foreground('terminal')

    def action_password(self):
        self.foreground('password')

    def action_setup_key(self):
        self.foreground('setup-key')

    def action_edit(self):
        self.foreground('edit')

    @work(group='operation', exclusive=False)
    async def sync_project(self, dry=False):
        if self.busy:
            return
        self.busy = True
        backend = self.backend
        self.output('Previewing changes…' if dry else 'Syncing incremental source changes…')
        self.status('Syncing… · polling paused')
        try:
            result = await asyncio.to_thread(backend.sync, dry)
            self.output(result)
            self.output('Preview complete; no source files transferred.' if dry else 'Sync complete. Existing job snapshots are unchanged.')
            self.show_profile()
        except (Error, OSError, subprocess.SubprocessError) as exc:
            self.output(str(exc))
            self.notify(str(exc), severity='error', timeout=10)
        finally:
            self.busy = False
            self.status('Finished · r refresh / c connect')

    @work(group='operation', exclusive=False)
    async def action_reconcile(self):
        if self.busy:
            return
        self.busy = True
        try:
            result = await asyncio.to_thread(self.backend.reconcile)
            self.output(result)
            self.notify(result, timeout=15)
        except (Error, OSError, ValueError) as exc:
            self.output(str(exc))
            self.notify(str(exc), severity='error', timeout=10)
        finally:
            self.busy = False

    def action_preview(self):
        self.sync_project(dry=True)

    def action_sync(self):
        self.sync_project()

    @work(group='operation', exclusive=False)
    async def action_add(self):
        if self.busy:
            return
        self.busy = True
        try:
            profile = await self.push_screen_wait(AddProject())
            if profile:
                if any(p.name == profile.name for p in self.profiles):
                    raise Error('That project name already exists.')
                self.profiles.append(profile)
                save_profiles(self.profiles)
                select = self.query_one('#project', Select)
                select.set_options([(p.name, p.name) for p in self.profiles])
                self.busy = False
                select.value = profile.name
        except Error as exc:
            self.notify(str(exc), severity='error')
        finally:
            self.busy = False

    def action_logs(self):
        job = self.selected_job()
        if not job:
            self.notify('Select a job first.')
            return
        try:
            changed = job != self.log_job
            self.log_job, self.log_backend = job, self.backend_for_job(job)
            if changed:
                self.log_text = ''
                self.query_one('#job-log', RichLog).clear()
                self.query_one('#log-status', Static).update(f'Job {job} · loading log…')
            self.read_logs()
        except Error as exc:
            self.notify(str(exc), severity='error')

    @work(group='logs', exclusive=True)
    async def read_logs(self):
        if not self.log_job:
            return
        backend, job, stderr = self.log_backend, self.log_job, self.stderr
        self.last_log = time.monotonic()
        try:
            text = await asyncio.to_thread(backend.logs, job, stderr)
            if job != self.log_job or backend is not self.log_backend or stderr != self.stderr:
                return
            if text != self.log_text:
                widget = self.query_one('#job-log', RichLog)
                widget.clear()
                widget.write(text)
                self.log_text = text
            self.update_log_status()
        except (Error, OSError) as exc:
            if job != self.log_job or backend is not self.log_backend or stderr != self.stderr:
                return
            self.log_follow = False
            self.query_one('#follow', Button).label = 'Follow: off'
            self.query_one('#log-status', Static).update(str(exc))

    def action_follow(self):
        if self.log_follow:
            self.log_follow = False
        else:
            self.action_logs()
            self.log_follow = bool(self.log_job)
        self.query_one('#follow', Button).label = 'Follow: ' + ('on' if self.log_follow else 'off')
        self.update_log_status()

    def update_log_status(self):
        if self.log_job:
            self.query_one('#log-status', Static).update(
                f'Job {self.log_job} · {"stderr" if self.stderr else "stdout"} · last 150 lines · '
                + ('follow every 10s' if self.log_follow else 'follow off · select another job to view its log'))

    def action_stderr(self):
        self.stderr = not self.stderr
        self.query_one('#stderr', Button).label = 'stdout' if self.stderr else 'stderr'
        if self.log_job:
            self.read_logs()

    @work(group='operation', exclusive=False)
    async def action_cancel(self):
        if self.busy:
            return
        job = self.selected_job()
        if not job:
            self.notify('Select a job first.')
            return
        self.busy = True
        try:
            if await self.push_screen_wait(Confirm(f'Cancel your Slurm job {job}? This stops its running tasks.')):
                await asyncio.to_thread(self.backend.cancel, job)
                self.notify('Cancellation requested for ' + job)
        except (Error, OSError) as exc:
            self.notify(str(exc), severity='error')
        finally:
            self.busy = False
        self.refresh_data(force=True)

    @work(group='operation', exclusive=False)
    async def action_download(self):
        if self.busy:
            return
        job = self.selected_job()
        if not job:
            self.notify('Select a job first.')
            return
        self.busy = True
        try:
            if await self.push_screen_wait(Confirm(f'Download results and logs for job {job}?\nCheckpoints can be large; this copies the complete result directory.')):
                result = await asyncio.to_thread(self.backend_for_job(job).download, job)
                self.output('Downloaded to ' + result)
                self.notify('Downloaded to ' + result)
        except (Error, OSError, subprocess.SubprocessError) as exc:
            self.notify(str(exc), severity='error', timeout=10)
        finally:
            self.busy = False

    async def action_quit(self):
        if self.busy:
            self.notify('Wait for the operation to finish before quitting; submission may already be accepted.', severity='warning')
            return
        self.exit()
