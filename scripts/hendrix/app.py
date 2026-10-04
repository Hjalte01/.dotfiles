"""Textual frontend. Explicit connection, modest polling, and bounded logs."""
from __future__ import annotations

import asyncio
import datetime as dt
import os
import shutil
import re
import shlex
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
                             Select, Static, TabbedContent, TabPane, OptionList)

from . import core
from .core import (Backend, CONFIG, Error, Profile, load_profiles, save_profiles,
                   summarize, validate_resources, visible_gpu_nodes, gpu_row_order, GPU_PREFERENCE, free_total, request_groups, gpu_request, atomic_json)
from .cli import connect, edit_profiles, setup_ssh, vpn


class NavigationTable(DataTable):
    BINDINGS = [Binding('h', 'cursor_left', show=False), Binding('j', 'cursor_down', show=False),
                Binding('k', 'cursor_up', show=False), Binding('l', 'cursor_right', show=False)]


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
    def __init__(self, question):
        super().__init__()
        self.question = question

    def compose(self):
        with Vertical(id='dialog'):
            yield Static(self.question, markup=False)
            with Horizontal():
                yield Button('Confirm', variant='primary', id='yes')
                yield Button('Back', id='no')

    def on_button_pressed(self, event):
        self.dismiss(event.button.id == 'yes')

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
                'hjkl: table arrows and menu navigation · Tab: next control\n'
                'Alt+h/l: change tabs · /: search · Esc: leave search\n'
                'c: connect · r: refresh · s: sync · p: sync preview · b: submit\n'
                'Shift+L: logs · q: quit · ?: this help\n\n'
                'GPU VIEW\n'
                'All resource counts are free(total). For example, 4(6) means four free of six.\n'
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
                'Compare memory fit, measured training speed and queue wait when choosing hardware.\n\n'
                'SELECTION AND COPY\n'
                'v: mark/unmark the focused node row · Shift+V: clear marks.\n'
                'y: copy a one-GPU model request for the marked rows or focused row/model.\n'
                'Shift+Y: review the request; optionally pin ONE exact node.\n'
                'Mixed-model selections open a chooser: Slurm GRES types are not an OR-list.\n'
                'Marking several nodes does not request several GPUs or a multi-node job.\n'
                'A model request leaves node choice to Slurm. An exact-node request may wait longer.\n'
                'Copies are saved locally in ~/.local/state/hendrix/copied-request.json as well.\n'
                'Selected rows stay marked across filters; refreshed inventory removes vanished rows.\n\n'
                'WORKFLOW\n'
                'Sync updates your source mirror; submit makes a separate source snapshot.\n'
                'Datasets and Python environments remain shared. Opening the app does not connect.\n'
                'Jobs poll every 30s, nodes every 60s; changing filters makes no cluster requests.\n'
                'After a lost submission response, use Reconcile before attempting another job.\n'
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


class SubmitForm(ModalScreen[tuple[dict, dict] | None]):
    def __init__(self, profile, models, chosen=None):
        super().__init__()
        self.profile, self.models, self.chosen = profile, models, chosen

    def compose(self):
        with VerticalScroll(id='dialog'):
            yield Label(f'Submit — {self.profile.name}')
            yield NavigationSelect([(p['name'], i) for i, p in enumerate(self.profile.presets)],
                         value=0, allow_blank=False, id='preset')
            yield Static('Sync first → isolated source snapshot → sbatch. No GPU fallback.', markup=False)
            yield Static('Discovered GPU names: ' + ', '.join(self.models or ['not queried yet']), markup=False)
            for ident, title, value in [
                ('model', 'GPU model (exact GRES name, or any)', self.chosen or 'a100'),
                ('gpus', 'GPU count', '1'), ('partition', 'Partition', 'gpu'),
                ('cpus', 'CPU count', '4'), ('memory', 'Host RAM (not GPU VRAM)', '32G'),
                ('time', 'Time limit', self.profile.presets[0].get('time', '00:30:00'))]:
                yield Label(title)
                yield Input(value=value, id='resource-' + ident)
            yield Static('', id='form-error', markup=False)
            with Horizontal():
                yield Button('Review request', variant='primary', id='review')
                yield Button('Back', id='back')

    def on_select_changed(self, event):
        if event.select.id == 'preset' and isinstance(event.value, int):
            self.query_one('#resource-time', Input).value = self.profile.presets[event.value].get('time', '00:30:00')

    def on_button_pressed(self, event):
        if event.button.id == 'back':
            self.dismiss(None)
            return
        try:
            resources = {key: self.query_one('#resource-' + key, Input).value.strip()
                         for key in ('model', 'gpus', 'partition', 'cpus', 'memory', 'time')}
            resources['gpus'], resources['cpus'] = int(resources['gpus']), int(resources['cpus'])
            validate_resources(resources)
            preset = self.profile.presets[self.query_one('#preset', Select).value]
            self.dismiss((preset, resources))
        except (ValueError, Error) as exc:
            self.query_one('#form-error', Static).update(str(exc))

    def key_escape(self):
        self.dismiss(None)


class HendrixApp(App):
    TITLE = 'Hendrix'
    SUB_TITLE = 'Local projects · Slurm GPUs · jobs'
    CSS = '''
    Screen { background: #101721; overflow: hidden; }
    Header { background: #192a40; height: 1; }
    #connection { height: 1; padding: 0 1; color: #92a9bb; }
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
    Select > SelectCurrent { border: round #36516c; background: #192332; }
    Select:focus > SelectCurrent { border: round #60c2d8; }
    SelectOverlay { border: round #60c2d8; background: #192332; max-height: 12; }
    #gpu-actions { height: 1; }
    #reasons { height: 1; min-width: 17; width: auto; border: none; padding: 0 1; background: #192a40; color: #a6d7ed; }
    #gpu-view-status { height: 1; width: 1fr; color: #92a9bb; text-align: right; }
    #models { height: 11; margin-bottom: 1; border: round #36516c; }
    #nodes { height: 1fr; min-height: 6; border: round #36516c; }
    DataTable > .datatable--header { background: #192a40; color: #a6d7ed; text-style: bold; }
    DataTable > .datatable--cursor { background: #294963; color: #ffffff; }
    #jobs { height: 1fr; min-height: 6; border: round #36516c; }
    #project-details { height: auto; margin: 1 0; }
    .actions { height: auto; min-height: 3; margin: 1 0; }
    #sync-output, #job-log { height: 1fr; border: round #36516c; }
    #log-status { height: auto; color: #92a9bb; }
    ModalScreen { align: center middle; background: #000000 65%; }
    #dialog, #help-dialog { width: 80; max-width: 95%; max-height: 95%; height: auto; border: thick #4c9ab8; padding: 1 2; background: #192332; }
    #help-dialog { height: 90%; }
    #dialog Static, #dialog Label, #help-dialog Static { height: auto; margin-bottom: 1; }
    #dialog Input, #dialog Select { margin-bottom: 1; }
    #dialog Horizontal { height: 3; }
    #form-error { color: #ff9e91; }
    .dialog-title { color: #a6d7ed; text-style: bold; }
    .muted { color: #92a9bb; }
    '''
    BINDINGS = [('q', 'quit', 'Quit'), ('c', 'connect', 'Connect'), ('r', 'refresh', 'Refresh'),
                ('s', 'sync', 'Sync'), ('p', 'preview', 'Preview'), ('b', 'submit', 'Submit'),
                ('L', 'logs', 'Logs'), ('e', 'edit', 'Profiles'), ('t', 'terminal', 'SSH'),
                ('?', 'help', 'Help'), Binding('/', 'search', 'Search', show=False),
                Binding('v', 'mark', 'Mark', show=False), Binding('V', 'clear_marks', 'Clear marks', show=False),
                Binding('y', 'yank', 'Copy GPU', show=False), Binding('Y', 'review_copy', 'Review copy', show=False),
                Binding('R', 'reasons', 'Reasons', show=False), Binding('=', 'default_sort', 'Default sort', show=False),
                Binding('h,k', 'previous_control', 'Previous control', show=False),
                Binding('j,l', 'next_control', 'Next control', show=False),
                Binding('alt+h', 'previous_tab', 'Previous tab', show=False),
                Binding('alt+l', 'next_tab', 'Next tab', show=False)]

    def __init__(self, project=None):
        super().__init__()
        self.profiles = load_profiles()
        self.profile = next((p for p in self.profiles if p.name == project), self.profiles[0])
        self.backend = Backend(self.profile)
        self.connected = False
        self.busy = False
        self.refreshing = False
        self.nodes = []
        self.jobs = []
        self.old_jobs = {}
        self.last_gpu = self.last_history = self.last_jobs = 0
        self.selected_model = None
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
            yield Button('? Help', id='help')
        with TabbedContent():
            with TabPane('GPUs', id='gpu-tab'):
                with Horizontal(id='gpu-controls'):
                    yield Input(placeholder='/ Search model, node, state…', id='node-filter')
                    yield NavigationSelect([('Healthy + free GPUs', 'candidates'), ('Healthy nodes', 'healthy'),
                                            ('All nodes', 'all'), ('Idle nodes', 'IDLE'), ('Mixed nodes', 'MIXED'),
                                            ('Allocated nodes', 'ALLOCATED'), ('Unavailable nodes', 'unavailable')],
                                           value='candidates', allow_blank=False, id='state-filter')
                with Horizontal(id='gpu-actions'):
                    yield Button('Reasons off (0)', id='reasons')
                    yield Static('', id='gpu-view-status', markup=False)
                yield NavigationTable(id='models', cursor_type='row')
                yield NavigationTable(id='nodes', cursor_type='row')
            with TabPane('Projects', id='project-tab'):
                yield Static('', id='project-details', markup=False)
                with Horizontal(classes='actions'):
                    yield Button('Preview', id='preview')
                    yield Button('Sync', id='sync', variant='primary')
                    yield Button('Submit', id='submit', variant='success')
                with Horizontal(classes='actions'):
                    yield Button('Add project', id='add')
                    yield Button('Edit profiles', id='edit')
                    yield Button('Reconcile', id='reconcile')
                with Horizontal(classes='actions'):
                    yield Button('Set VPN password', id='password')
                    yield Button('Setup SSH key', id='setup-key')
                yield RichLog(id='sync-output', wrap=True, markup=False, max_lines=1000)
            with TabPane('Jobs', id='jobs-tab'):
                yield NavigationTable(id='jobs', cursor_type='row')
                with Horizontal(classes='actions'):
                    yield Button('Logs', id='logs')
                    yield Button('Follow: off', id='follow')
                    yield Button('stderr', id='stderr')
                    yield Button('Download results', id='download')
                    yield Button('Cancel job', id='cancel', variant='error')
                yield Static('Select a job and open its logs. Tail is limited to the last 150 lines.', id='log-status', markup=False)
                yield RichLog(id='job-log', wrap=True, markup=False, max_lines=150)
        yield Footer()

    def on_mount(self):
        self.render_nodes()
        self.query_one('#jobs', DataTable).add_columns('Job', 'Project / name', 'State', 'Elapsed', 'Limit', 'Node / pending reason', 'GPU / resources', 'Exit')
        self.show_profile()
        self.set_interval(5, self.tick)

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
        self.marked_rows.clear()
        self.selected_model = None
        self.last_gpu = self.last_history = self.last_jobs = 0
        self.log_job, self.log_follow = None, False
        self.query_one('#follow', Button).label = 'Follow: off'
        for ident in ('models', 'nodes', 'jobs'):
            self.query_one('#' + ident, DataTable).clear()
        self.query_one('#job-log', RichLog).clear()
        self.status('Project changed · c connect / r refresh')
        self.render_nodes()
        self.show_profile()

    def on_input_changed(self, event):
        if event.input.id == 'node-filter':
            self.render_nodes()

    def on_data_table_row_selected(self, event):
        if event.data_table.id == 'models':
            self.selected_model = str(event.row_key.value)
            self.notify(f'Next submission GPU: {self.selected_model}')

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
        if key in ('cpu', 'ram', 'gpu'):
            value = free if key == 'gpu' else node.get(key + '_free')
            # Unknown values stay last, irrespective of sort direction.
            return (value is None, (-value if self.sort_reverse else value) if value is not None else 0,
                    model, node['name'])
        value = model.lower() if key == 'model' else node['name'] if key == 'node' else node['state']
        return (value, node['name'], model)

    def resource_text(self, free, total, *, gib=False):
        style = '#6cdbc0' if free is not None and free > 0 else '#e9bf6a' if free is None else '#8294a7'
        return Text(free_total(free, total, gib=gib), style=style)

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
        widths = [('node', 'Node', node_width),
                  ('model', 'Model', 9), ('gpu', 'GPU', 6),
                  ('cpu', 'CPU', 8), ('ram', 'RAM GiB', 14), ('state', 'State', 9)]
        for key, label, width in widths:
            table.add_column(self.header_label(key, label), key=key, width=width)
        if self.show_reasons and reasons:
            table.add_column('Unavailable reason', key='reason', width=36)
        self.node_rows = {}
        for index, (n, model) in enumerate(rows):
            row_key = n['name'] + ':' + model
            self.node_rows[row_key] = (n['name'], model)
            marked = (n['name'], model) in self.marked_rows
            name = display_names[n['name']]
            free = max(0, n['capacity'][model] - n['used'][model]) if n['used'][model] is not None else None
            state_style = '#e8a099' if not n['eligible'] else '#6cdbc0' if n['state'] == 'IDLE' else '#e9bf6a'
            cells = [Text(name + (' ●' if marked else ''),
                          style='bold #60c2d8' if marked else '#d4e0eb'), model,
                     self.resource_text(free, n['capacity'][model]),
                     self.resource_text(n.get('cpu_free'), n.get('cpu_total')),
                     self.resource_text(n.get('ram_free'), n.get('ram_total'), gib=True),
                     Text(n['state'], style=state_style, overflow='ellipsis', no_wrap=True)]
            if self.show_reasons and reasons:
                cells.append(n.get('reason', ''))
            table.add_row(*cells, key=row_key)
            if row_key == previous:
                table.move_cursor(row=index, scroll=False)
        table.scroll_to(x=horizontal, animate=False)
        table.border_title = 'Nodes · free(total)'
        table.border_subtitle = 'v mark · y copy'
        models.clear(columns=True)
        for key, label, width in [('model', 'Model', 12), ('gpu', 'GPU', 10), ('cpu', 'CPU', 13), ('ram', 'RAM GiB', 16)]:
            models.add_column(self.header_label(key, label), key=key, width=width)
        totals = summarize(nodes)
        if self.sort_key == 'preference':
            totals.sort(key=lambda r: (GPU_PREFERENCE.get(r['model'].lower(), 99), r['model']))
        elif self.sort_key in ('gpu', 'cpu', 'ram'):
            field = 'unallocated' if self.sort_key == 'gpu' else self.sort_key + '_free'
            flag = 'unknown' if self.sort_key == 'gpu' else field + '_unknown'
            totals.sort(key=lambda r: (r[flag], -r[field] if self.sort_reverse else r[field], r['model']))
        else:
            totals.sort(key=lambda r: r['model'], reverse=self.sort_reverse if self.sort_key == 'model' else False)
        for index, row in enumerate(totals):
            gpu = None if row['unknown'] else row['unallocated']
            cpu_free = None if row['cpu_free_unknown'] else row['cpu_free']
            cpu_total = None if row['cpu_total_unknown'] else row['cpu_total']
            ram_free = None if row['ram_free_unknown'] else row['ram_free']
            ram_total = None if row['ram_total_unknown'] else row['ram_total']
            models.add_row(Text(row['model'], style='bold #a6d7ed'), self.resource_text(gpu, row['total']),
                           self.resource_text(cpu_free, cpu_total), self.resource_text(ram_free, ram_total, gib=True),
                           key=row['model'])
            if row['model'] == previous_model:
                models.move_cursor(row=index, scroll=False)
        models.styles.height = min(12, max(4, len(totals) + 3))
        models.border_title = 'Models · free(total)'
        models.border_subtitle = 'Click a heading to sort'
        total = sum(len(n['capacity']) for n in self.nodes)
        self.query_one('#gpu-view-status', Static).update(
            f'{len(rows)}/{total} rows · {len(self.marked_rows)} marked · '
            + ('preference' if self.sort_key == 'preference' else self.sort_key + (' ↓' if self.sort_reverse else ' ↑')))

    def on_data_table_header_selected(self, event):
        if event.data_table.id not in ('models', 'nodes'):
            return
        key = str(event.column_key.value)
        if key not in ('node', 'model', 'gpu', 'cpu', 'ram', 'state'):
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
        self.query_one(TabbedContent).active = 'gpu-tab'
        self.query_one('#node-filter', Input).focus()

    def key_escape(self):
        if self.focused is self.query_one('#node-filter', Input):
            self.query_one('#nodes', DataTable).focus()

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
        panes = ['gpu-tab', 'project-tab', 'jobs-tab']
        tabs.active = panes[(panes.index(tabs.active) + direction) % len(panes)]
        target = {'gpu-tab': '#nodes', 'project-tab': '#sync', 'jobs-tab': '#jobs'}[tabs.active]
        self.query_one(target).focus()

    def action_previous_tab(self):
        self.change_tab(-1)

    def action_next_tab(self):
        self.change_tab(1)

    def render_jobs(self):
        table = self.query_one('#jobs', DataTable)
        selected = self.selected_job()
        table.clear()
        records = {r.get('job_id'): r for r in self.backend.history() if r.get('host') == self.profile.host}
        for job in sorted(self.jobs, key=lambda j: int(re.match(r'\d+', j['id'])[0]), reverse=True):
            record = records.get(job['id'], {})
            table.add_row(job['id'], record.get('project', job['name']), job['state'], job['elapsed'],
                          job['limit'], job['reason'], job['gpu'], job.get('exit', ''), key=job['id'])
        if selected:
            for index, job in enumerate(sorted(self.jobs, key=lambda j: int(re.match(r'\d+', j['id'])[0]), reverse=True)):
                if job['id'] == selected:
                    table.move_cursor(row=index)
                    break

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

    @work(group='refresh', exclusive=False)
    async def refresh_data(self, force=False):
        if self.busy or self.refreshing:
            return
        self.refreshing = True
        backend = self.backend
        try:
            now = time.monotonic()
            history = force or now - self.last_history >= 60
            jobs = await asyncio.to_thread(backend.jobs, history)
            if backend is not self.backend:
                return
            if history:
                self.old_jobs = {j['id']: j for j in jobs if j['state'] not in ('PENDING', 'RUNNING', 'COMPLETING')}
                self.last_history = now
            combined = dict(self.old_jobs)
            current_ids = {j['id'] for j in jobs}
            for previous in self.jobs:
                if previous['id'] not in current_ids and previous['id'] not in combined:
                    combined[previous['id']] = {**previous, 'state': 'AWAITING_ACCOUNTING'}
            combined.update({j['id']: j for j in jobs})
            self.jobs = list(combined.values())
            self.last_jobs = now
            self.render_jobs()
            if force or now - self.last_gpu >= 60:
                nodes = await asyncio.to_thread(backend.nodes)
                if backend is not self.backend:
                    return
                self.nodes = nodes
                self.last_gpu = now
                self.render_nodes()
            self.connected = True
            self.status(f'{self.profile.host} · updated {time.strftime("%H:%M:%S")}'
                        + (' · accounting unavailable' if backend.accounting_warning else ''))
        except (Error, OSError, ValueError) as exc:
            if backend is self.backend:
                self.connected = False
                self.log_follow = False
                self.query_one('#follow', Button).label = 'Follow: off'
                self.status('Disconnected · c reconnect / r retry')
                self.connection_detail += '\n' + str(exc)
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
        try:
            with self.suspend():
                if action == 'connect':
                    connect(self.backend)
                elif action == 'terminal':
                    connect(self.backend)
                    subprocess.run(self.backend.ssh_argv(batch=False))
                elif action == 'password':
                    vpn('password', ['set'])
                elif action == 'setup-key':
                    connect(self.backend)
                    setup_ssh(self.backend)
                elif action == 'edit':
                    edit_profiles()
            if action == 'edit':
                self.profiles = load_profiles()
                self.profile = next((p for p in self.profiles if p.name == self.profile.name), self.profiles[0])
                self.backend = Backend(self.profile)
                select = self.query_one('#project', Select)
                select.set_options([(p.name, p.name) for p in self.profiles])
                select.value = self.profile.name
                self.show_profile()
            self.output(f'{action}: completed')
        except (Error, OSError, ValueError, subprocess.SubprocessError) as exc:
            self.output(str(exc))
            self.notify(str(exc), severity='error', timeout=10)
        finally:
            self.busy = False
        if action in ('connect', 'terminal', 'setup-key'):
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
    async def action_submit(self):
        if self.busy:
            return
        if not self.profile.presets:
            self.notify('Add a batch-script preset using Edit profiles first.', severity='warning')
            return
        self.busy = True
        try:
            models = sorted({model for n in self.nodes for model in n['capacity']})
            request = await self.push_screen_wait(SubmitForm(self.profile, models, self.selected_model))
            if request is None:
                return
            preset, resources = request
            summary = ('Sync project source and submit an isolated snapshot?\n\n'
                       f'{self.profile.name} → {self.profile.host}\n'
                       f'Batch script: {shlex.join([preset["script"], *preset.get("args", [])])}\n'
                       + '\n'.join(f'{key}: {value}' for key, value in resources.items()) +
                       '\n\nDatasets and the existing environment remain shared. Jobs may queue. No GPU fallback.')
            if not await self.push_screen_wait(Confirm(summary)):
                return
            self.output('Syncing and preparing a job snapshot…')
            result = await asyncio.to_thread(self.backend.submit, preset, resources)
            self.output(f'Submitted job {result["job_id"]}\nSnapshot: {result["snapshot"]}\nLogs: {result["output"]}')
            self.show_profile()
            self.notify('Submitted job ' + result['job_id'])
        except (Error, OSError, ValueError, subprocess.SubprocessError) as exc:
            self.output(str(exc))
            self.notify(str(exc), severity='error', timeout=15)
        finally:
            self.busy = False
        self.refresh_data(force=True)

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
            self.log_job, self.log_backend = job, self.backend_for_job(job)
            self.log_text = ''
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
            if job != self.log_job or stderr != self.stderr:
                return
            if text != self.log_text:
                widget = self.query_one('#job-log', RichLog)
                widget.clear()
                widget.write(text)
                self.log_text = text
            self.query_one('#log-status', Static).update(f'Job {job} · {"stderr" if stderr else "stdout"} · last 150 lines · follow every 10s')
        except (Error, OSError) as exc:
            self.log_follow = False
            self.query_one('#follow', Button).label = 'Follow: off'
            self.query_one('#log-status', Static).update(str(exc))

    def action_follow(self):
        if not self.log_job:
            self.action_logs()
        self.log_follow = bool(self.log_job) and not self.log_follow
        self.query_one('#follow', Button).label = 'Follow: ' + ('on' if self.log_follow else 'off')

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
