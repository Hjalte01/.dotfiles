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
                             Select, Static, TabbedContent, TabPane, OptionList, Collapsible)

from dotfiles_theme import install as install_theme, color as theme_color

from . import core
from .core import (Backend, CONFIG, Error, Profile, load_profiles, save_profiles,
                   summarize, validate_resources, visible_gpu_nodes, gpu_row_order, GPU_PREFERENCE, free_total, request_groups, gpu_request, atomic_json)
from .cli import connect, edit_profiles, setup_ssh, vpn


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
                '1: GPU models · 2: GPU nodes · 3: Projects · 4: Jobs · 5: Logs · 6: Cluster queue\n'
                'hjkl: table arrows and menu navigation · Tab / Shift+Tab: next / previous control\n'
                'g/G: first/last table row · Ctrl+d/u: page down/up\n'
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
                'QUEUE AND COMPARISON\n'
                '6: visible pending demand by partition; default gpu, or all visible partitions.\n'
                'Compact arrays show pending task counts and concurrency caps without expanding tasks.\n'
                'Waiting = Resources/Priority. Blocked = dependencies, holds, array caps, future starts.\n'
                'Other scheduler reasons stay explicit; explanations preserve the raw Slurm reason.\n'
                'Any GPU demand is separate. Counts are visible demand, never jobs ahead of you.\n'
                'Click Pending tasks to sort; GPU sorts free capacity; = restores model preference.\n'
                'In the launch form, c / Compare GPUs opens a comparison for the current script/resources.\n'
                'Enter minimum nominal GB of VRAM per GPU including headroom, or leave it unknown.\n'
                'Compare sends the actual local script to sbatch --test-only, only when pressed.\n'
                'No job, sync, snapshot, history or settings write is made by comparison.\n'
                'A100 is 40/80 GB; aliases and installed variants may be unknown. Host RAM is separate.\n'
                'Observed fit checks GPU/CPU/RAM together on a healthy node; complex topology is unknown.\n'
                'A star marks earliest predicted start among choices likely to meet entered VRAM.\n'
                'Speed is unmeasured; start estimates can change and do not predict completion.\n'
                'u / Use this model selects one model/count. Changing settings/script invalidates estimates.\n'
                'NVIDIA specifications describe hardware support, not installed NVLink connectivity.\n\n'
                'SELECTION AND COPY\n'
                'v: mark/unmark the focused node or model · Shift+V: clear marks.\n'
                'y: copy a one-GPU model request for the marked rows or focused row/model.\n'
                'Shift+Y: review the request; optionally pin ONE exact node.\n'
                'Mixed-model selections open a chooser: Slurm GRES types are not an OR-list.\n'
                'Marking several nodes does not request several GPUs or a multi-node job.\n'
                'A model request leaves node choice to Slurm. An exact-node request may wait longer.\n'
                'Copies are saved locally in ~/.local/state/hendrix/copied-request.json as well.\n'
                'Selected rows stay marked across filters; refreshed inventory removes vanished rows.\n\n'
                'WORKFLOW\n'
                'b uses marked GPU models, or the focused GPU row. Space toggles models in the form.\n'
                'h/l or −/+: choose GPU count per model. Each selected model launches a separate job.\n'
                'a: advanced settings · b / Ctrl+Enter: review · Esc: leave field / close form\n'
                'CPU/RAM/time/partition and GPU counts are remembered per project and script.\n'
                'Sync updates your source mirror; submit makes a separate source snapshot.\n'
                'Datasets and Python environments remain shared. Opening the app does not connect.\n'
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


class GPUChoices(NavigationTable):
    BINDINGS = [Binding('space,enter', 'toggle_gpu', show=False),
                Binding('+,equals,l', 'increase_gpu', show=False),
                Binding('-,h', 'decrease_gpu', show=False)]

    def __init__(self, models, counts, inventory, **kwargs):
        super().__init__(cursor_type='row', **kwargs)
        self.models, self.counts, self.inventory = models, counts, inventory

    def on_mount(self):
        self.add_columns('Use', 'GPU model', 'GPUs / job', 'Free(total)', 'Max / job')
        for model in self.models:
            totals = self.inventory.get(model)
            self.add_row('', model, '', free_total(*totals[:2]) if totals else '?',
                         str(self.limit(model)), key=model)
        self.styles.height = min(8, self.row_count + 1)
        self.refresh_counts()

    def limit(self, model):
        totals = self.inventory.get(model)
        return min(8, totals[2]) if totals else 8

    def refresh_counts(self):
        for model in self.models:
            count = self.counts.get(model, 0)
            self.update_cell(model, self.ordered_columns[0].key, '✓' if count else '·')
            self.update_cell(model, self.ordered_columns[2].key, str(count))

    def current_model(self):
        return self.models[self.cursor_row] if self.models else None

    def action_toggle_gpu(self):
        model = self.current_model()
        if model:
            self.counts[model] = 0 if self.counts.get(model) else 1
            self.refresh_counts()

    def action_increase_gpu(self):
        model = self.current_model()
        if model:
            self.counts[model] = min(self.limit(model), self.counts.get(model, 0) + 1)
            self.refresh_counts()

    def action_decrease_gpu(self):
        model = self.current_model()
        if model:
            self.counts[model] = max(0, self.counts.get(model, 0) - 1)
            self.refresh_counts()


class SubmitForm(ModalScreen[tuple[dict, list[dict]] | None]):
    BINDINGS = [Binding('a', 'advanced', 'Advanced', show=False),
                Binding('c', 'compare', 'Compare GPUs', show=False),
                Binding('b,ctrl+enter', 'review', 'Review', show=False)]

    def __init__(self, profile, models, chosen=None, selected=None, inventory=None,
                 backend=None, nodes=None, queue=None, freshness=''):
        super().__init__()
        self.profile = profile
        self.settings = core.load_launch_settings()
        last = self.settings['last_presets'].get(core.launch_key(profile, {'script': '', 'args': []}))
        self.preset_index = next((i for i, p in enumerate(profile.presets)
                                  if core.launch_key(profile, p) == last), 0)
        self.auto_run_name = core.default_run_name(profile, profile.presets[self.preset_index])
        self.run_name = self.auto_run_name
        self.selection = list(selected or [])
        saved = self.saved_requests(self.preset_index)
        if not self.selection and chosen and not saved:
            self.selection = [chosen]
        self.models = sorted(set(models) | set(self.selection) | {r['model'] for r in saved},
                             key=lambda m: (GPU_PREFERENCE.get(m.lower(), 99), m))
        if not self.models:
            self.models = ['a100']
        if 'any' not in self.models:
            self.models.append('any')
        self.inventory = inventory or {}
        self.backend = backend or Backend(profile)
        self.nodes, self.queue = nodes or [], queue
        self.freshness = freshness
        self.minimum_vram = self.saved_guidance(self.preset_index)
        self.counts = {}
        self.drafts = {}
        self.reset_counts(saved)

    def saved_requests(self, index):
        preset = self.profile.presets[index]
        return self.settings['requests'].get(core.launch_key(self.profile, preset), [])

    def saved_guidance(self, index):
        return self.settings['guidance'].get(core.launch_key(self.profile, self.profile.presets[index]), {}).get('minimum_vram', '')

    def defaults(self, index):
        saved = self.saved_requests(index)
        return saved[0] if saved else dict(partition='gpu', cpus=4, memory='32G',
                                         time=self.profile.presets[index].get('time', '00:30:00'))

    def reset_counts(self, saved):
        previous = {r['model']: r['gpus'] for r in saved}
        models = self.selection or list(previous) or [self.models[0]]
        self.counts.clear()
        self.counts.update({model: previous.get(model, 1) for model in models})

    def compose(self):
        defaults = self.defaults(self.preset_index)
        with VerticalScroll(id='dialog', classes='launch-dialog'):
            yield Label(f'Run — {self.profile.name}')
            yield NavigationSelect([(p['name'], i) for i, p in enumerate(self.profile.presets)],
                                   value=self.preset_index, allow_blank=False, id='preset')
            with Horizontal(id='run-name-row'):
                yield Label('Run name:', id='run-name-label')
                yield Input(value=self.run_name, id='run-name')
            yield Static('Each selected model runs the script as a separate job.', markup=False)
            yield GPUChoices(self.models, self.counts, self.inventory, id='submit-gpus')
            yield Static('j/k move · Space select · h/l or −/+ count · c Compare · a Advanced · b review', classes='muted')
            yield Static('', id='resource-summary', markup=False)
            with Collapsible(title='Advanced settings (a)', collapsed=True, id='advanced'):
                yield Static('CPUs: data loading/workers · RAM: host-memory needs · Time: longer runs\n'
                             'Partition: only change if you have access. Defaults are saved per script.', classes='muted')
                for ident, title in [('partition', 'Partition'), ('cpus', 'CPU count per job'),
                                     ('memory', 'Host RAM per job'), ('time', 'Time limit per job')]:
                    yield Label(title)
                    yield Input(value=str(defaults[ident]), id='resource-' + ident)
                yield Label('Minimum VRAM per GPU (nominal GB, including headroom; optional)')
                yield Input(value=str(self.minimum_vram), placeholder='Blank: workload memory needs unknown', id='minimum-vram')
                yield Label('Add an exact GPU model (if missing from inventory)')
                yield Input(placeholder='Exact GRES name', id='custom-model')
                yield Button('Add GPU model', id='add-model')
            yield Static('', id='form-error', markup=False)
            with Horizontal(id='launch-buttons'):
                yield Button('Review request', variant='primary', id='review')
                yield Button('Compare GPUs', id='compare')
                yield Button('Back', id='back')

    def on_mount(self):
        self.update_summary()
        self.query_one('#submit-gpus').focus()

    def update_summary(self):
        values = {key: self.query_one('#resource-' + key, Input).value
                  for key in ('partition', 'cpus', 'memory', 'time')}
        self.query_one('#resource-summary', Static).update(
            f"Per job: {values['cpus']} CPUs · {values['memory']} RAM · {values['time']} · {values['partition']}")

    def on_input_changed(self, event):
        if event.input.id == 'minimum-vram':
            self.minimum_vram = event.value
        if event.input.id.startswith('resource-') and self.is_mounted:
            self.update_summary()

    def on_select_changed(self, event):
        if event.select.id != 'preset' or not isinstance(event.value, int) or not self.is_mounted:
            return
        if event.value == self.preset_index:
            return
        self.drafts[self.preset_index] = (self.counts.copy(), {
            key: self.query_one('#resource-' + key, Input).value
            for key in ('partition', 'cpus', 'memory', 'time')}, self.minimum_vram)
        self.preset_index = event.value
        field = self.query_one('#run-name', Input)
        updated = core.default_run_name(self.profile, self.profile.presets[event.value])
        if field.value == self.auto_run_name:
            field.value = updated
        self.auto_run_name = updated
        if event.value in self.drafts:
            counts, defaults, self.minimum_vram = self.drafts[event.value]
            self.counts.clear()
            self.counts.update(counts)
        else:
            self.minimum_vram = self.saved_guidance(event.value)
            defaults = self.defaults(event.value)
            saved = self.saved_requests(event.value)
            table = self.query_one('#submit-gpus', GPUChoices)
            for request in saved:
                if request['model'] not in self.models:
                    self.models.append(request['model'])
                    table.add_row('', request['model'], '', '?', '8', key=request['model'])
            self.reset_counts(saved)
        self.query_one('#submit-gpus', GPUChoices).refresh_counts()
        for key in ('partition', 'cpus', 'memory', 'time'):
            self.query_one('#resource-' + key, Input).value = str(defaults[key])
        self.query_one('#minimum-vram', Input).value = str(self.minimum_vram)
        self.update_summary()

    def action_advanced(self):
        advanced = self.query_one('#advanced', Collapsible)
        advanced.collapsed = not advanced.collapsed
        if advanced.collapsed:
            self.query_one('#submit-gpus').focus()
        else:
            self.query_one('#resource-partition').focus()

    def add_model(self):
        field = self.query_one('#custom-model', Input)
        model = field.value.strip()
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', model) or model.startswith('-'):
            raise Error('Enter an exact Slurm GPU model name.')
        table = self.query_one('#submit-gpus', GPUChoices)
        if model not in self.models:
            self.models.append(model)
            table.add_row('', model, '', '?', '8', key=model)
        self.counts[model] = self.counts.get(model) or 1
        table.refresh_counts()
        table.move_cursor(row=self.models.index(model))
        table.focus()
        field.value = ''

    def action_review(self):
        try:
            self.run_name = core.validate_run_name(self.query_one('#run-name', Input).value.strip())
            core.minimum_vram(self.minimum_vram)
            common = {key: self.query_one('#resource-' + key, Input).value.strip()
                      for key in ('partition', 'cpus', 'memory', 'time')}
            common['cpus'] = int(common['cpus'])
            requests = [dict(common, model=model, gpus=count) for model, count in self.counts.items() if count]
            if not requests:
                raise Error('Select at least one GPU model with Space or +.')
            for resources in requests:
                validate_resources(resources)
                limit = self.query_one('#submit-gpus', GPUChoices).limit(resources['model'])
                if resources['gpus'] > limit:
                    raise Error(f'{resources["model"]}: at most {limit} GPUs per job in this inventory.')
            self.dismiss((self.profile.presets[self.preset_index], requests))
        except (ValueError, Error) as exc:
            self.query_one('#form-error', Static).update(str(exc))

    def action_compare(self):
        try:
            common = {key: self.query_one('#resource-' + key, Input).value.strip()
                      for key in ('partition', 'cpus', 'memory', 'time')}
            common['cpus'] = int(common['cpus'])
            focused = self.query_one('#submit-gpus', GPUChoices).current_model()
            count = self.counts.get(focused) or 1
            validate_resources(dict(common, model='any', gpus=count))
            core.minimum_vram(self.minimum_vram)
            self.app.push_screen(CompareGPUs(self.backend, self.profile.presets[self.preset_index],
                                            common, count, self.minimum_vram, self.nodes,
                                            self.queue, self.freshness), self.comparison_done)
        except (ValueError, Error) as exc:
            self.query_one('#form-error', Static).update(str(exc))

    def comparison_done(self, result):
        self.minimum_vram = result['minimum_vram']
        self.query_one('#minimum-vram', Input).value = self.minimum_vram
        if result.get('model'):
            self.counts.clear()
            self.counts[result['model']] = result['gpus']
            table = self.query_one('#submit-gpus', GPUChoices)
            table.refresh_counts()
            table.move_cursor(row=self.models.index(result['model']))
        self.query_one('#submit-gpus').focus()

    def on_button_pressed(self, event):
        event.stop()
        if event.button.id == 'back':
            self.dismiss(None)
        elif event.button.id == 'review':
            self.action_review()
        elif event.button.id == 'compare':
            self.action_compare()
        elif event.button.id == 'add-model':
            try:
                self.add_model()
            except Error as exc:
                self.query_one('#form-error', Static).update(str(exc))

    def key_escape(self):
        advanced = self.query_one('#advanced', Collapsible)
        if isinstance(self.focused, Input):
            self.query_one('#submit-gpus').focus()
        elif not advanced.collapsed:
            advanced.collapsed = True
            self.query_one('#submit-gpus').focus()
        else:
            self.dismiss(None)


class CompareGPUs(ModalScreen[dict]):
    BINDINGS = [Binding('c', 'compare', 'Compare', show=False),
                Binding('u', 'use', 'Use this model', show=False)]

    def __init__(self, backend, preset, common, count, minimum, nodes, queue, freshness=''):
        super().__init__()
        self.backend, self.preset, self.common = backend, dict(preset), dict(common)
        self.count, self.minimum = str(count), str(minimum)
        self.nodes, self.queue, self.freshness = list(nodes), queue, freshness
        self.models = sorted({m for n in nodes if core.in_partition(n, common['partition']) for m in n['capacity']},
                             key=lambda m: (GPU_PREFERENCE.get(m.lower(), 99), m))
        self.script = backend.read_script(preset)
        self.estimates = {}
        self.running = False
        self.revision = 0
        self.state = 'Not queried · press Compare for scheduler estimates'

    def compose(self):
        with VerticalScroll(id='dialog', classes='comparison-dialog'):
            yield Static('Compare GPUs', classes='dialog-title')
            yield Static(f"{shlex.join([self.preset['script'], *map(str, self.preset.get('args', []))])}\n"
                         f"{self.common['partition']} · {self.common['cpus']} CPUs/task · "
                         f"{self.common['memory']} host RAM/node · {self.common['time']} limit\n{self.freshness}", markup=False)
            yield Label('GPUs per job (same request for every model)')
            yield Input(value=self.count, id='compare-count')
            yield Label('Minimum VRAM per GPU (nominal GB; include headroom, or leave blank)')
            yield Input(value=self.minimum, id='compare-vram')
            yield Static('', id='compare-status', markup=False)
            yield NavigationTable(id='comparison', cursor_type='row')
            yield Static('', id='compare-detail', markup=False)
            yield Static('Observed resource fit uses healthy individual nodes; scheduling is advisory.\n'
                         'Training speed unmeasured; predicted start does not predict completion.\n'
                         'c Compare · u Use this model · Esc Back · h/l scroll columns', classes='muted')
            with Horizontal():
                yield Button('Compare', id='run-compare', variant='primary')
                yield Button('Use this model', id='use-model')
                yield Button('Back', id='compare-back')

    def on_mount(self):
        self.render_comparison()
        self.query_one('#comparison').focus()
        self.set_interval(1, self.check_script)

    def check_script(self):
        try:
            current = self.backend.read_script(self.preset)
        except Error as exc:
            current = None
            self.state = str(exc)
        if current != self.script:
            self.script = current
            self.invalidate('Script changed · estimates invalidated; press Compare again')

    def invalidate(self, message):
        self.revision += 1
        self.estimates.clear()
        self.state = message
        self.render_comparison()

    def on_input_changed(self, event):
        if event.input.id in ('compare-count', 'compare-vram') and self.is_mounted:
            self.count = self.query_one('#compare-count', Input).value
            self.minimum = self.query_one('#compare-vram', Input).value
            self.invalidate('Request changed · estimates invalidated; press Compare again')

    def request(self, model):
        resources = dict(self.common, model=model, gpus=int(self.count))
        validate_resources(resources)
        core.minimum_vram(self.minimum)
        return resources

    def current_model(self):
        table = self.query_one('#comparison', DataTable)
        if table.row_count:
            return str(table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value)
        return None

    def render_comparison(self):
        if not self.is_mounted or not self.query('#comparison'):
            return
        table = self.query_one('#comparison', DataTable)
        previous, horizontal = self.current_model(), table.scroll_x
        table.clear(columns=True)
        for key, label, width in [('model', 'Model', 11), ('vram', 'VRAM/GPU', 12),
                                  ('memory', 'Memory assessment', 28), ('fit', 'Observed resource fit', 42),
                                  ('pending', 'Visible pending tasks', 36), ('start', 'Predicted start (local)', 28),
                                  ('at', 'Queried (local)', 22)]:
            table.add_column(label, key=key, width=width)
        demand = core.pending_demand(self.queue, self.common['partition']) if self.queue is not None else None
        eligible = []
        try:
            self.request('any')
            for model, estimate in self.estimates.items():
                if estimate['start'] and core.gpu_metadata(model, self.minimum)['assessment'] == 'likely fits by specification':
                    eligible.append(estimate['start'])
            earliest = min(eligible) if eligible else None
            error = ''
        except (ValueError, Error) as exc:
            earliest, error = None, str(exc)
        for index, model in enumerate(self.models):
            metadata = core.gpu_metadata(model, self.minimum if not error else None)
            fit = core.observed_fit(self.nodes, self.request(model), self.script) if not error and self.script else 'unknown'
            estimate = self.estimates.get(model)
            start = estimate['start'] if estimate else None
            best = earliest is not None and start == earliest and metadata['assessment'] == 'likely fits by specification'
            label = core.display_time(start) if estimate else 'not queried'
            if estimate and estimate['error']:
                label = 'scheduler error'
            table.add_row(Text(model + (' ★' if best else ''), style=theme_color("green") if best else ''),
                          metadata['vram'], metadata['assessment'], fit,
                          core.demand_text(demand.get(model)) if demand is not None else 'unavailable',
                          label, core.display_time(estimate['at']) if estimate else '—', key=model)
            if model == previous:
                table.move_cursor(row=index, scroll=False)
        table.scroll_to(x=horizontal, animate=False)
        table.styles.height = min(11, max(4, len(self.models) + 3))
        self.query_one('#compare-status', Static).update(error or (self.state +
            ('\n★ Earliest predicted start among choices likely to meet minimum VRAM' if earliest else
             '\nNo earliest fitting choice: enter minimum VRAM and obtain available estimates')))
        self.query_one('#run-compare', Button).disabled = self.running or not self.models or self.script is None
        self.query_one('#use-model', Button).disabled = self.running or bool(error) or not self.models
        self.show_detail()

    def show_detail(self):
        model = self.current_model()
        if model is None:
            self.query_one('#compare-detail', Static).update('No inventoried models in this partition; refresh inventory or choose another partition.')
            return
        metadata = core.gpu_metadata(model)
        cells = self.query_one('#comparison', DataTable).get_row(model)
        estimate = self.estimates.get(model)
        self.query_one('#compare-detail', Static).update(
            f"{model}: {cells[1]} · {cells[2]}\nObserved resource fit: {cells[3]}\n"
            f"Visible pending demand: {cells[4]}\nPredicted start: {cells[5]} · queried {cells[6]}\n"
            + ('Scheduler: ' + estimate['detail'] + '\n' if estimate else '')
            + ('Specification: ' + metadata['source'] if metadata['source'] else 'Hardware identity/VRAM unknown')
            + '\nInstalled NVLink connectivity is unknown.')

    def on_data_table_row_highlighted(self, event):
        if event.data_table.id == 'comparison' and self.is_mounted:
            self.show_detail()

    @work(group='gpu-estimates', exclusive=False)
    async def action_compare(self):
        if self.running or not self.models:
            return
        self.check_script()
        try:
            self.request('any')
            if self.script is None:
                raise Error('Local batch script is unavailable')
        except (ValueError, Error) as exc:
            self.state = str(exc)
            self.render_comparison()
            return
        self.running = True
        revision, script = self.revision, self.script
        requests = {model: self.request(model) for model in self.models}
        self.estimates.clear()
        try:
            for index, model in enumerate(self.models, 1):
                self.state = f'Comparing {index}/{len(self.models)}: {model} · test-only; no job created'
                self.render_comparison()
                try:
                    estimate = await asyncio.to_thread(self.backend.estimate, self.preset, requests[model], script)
                except (Error, OSError, ValueError, subprocess.SubprocessError) as exc:
                    estimate = dict(start=None, at=dt.datetime.now().astimezone(), detail=str(exc), error=True)
                if not self.is_mounted:
                    return
                self.check_script()
                if self.revision != revision:
                    return
                self.estimates[model] = estimate
            self.state = 'Comparison complete · estimates may change; no job created'
        finally:
            self.running = False
            if self.is_mounted:
                self.render_comparison()

    def action_use(self):
        model = self.current_model()
        if self.running or model is None:
            return
        try:
            resources = self.request(model)
        except (ValueError, Error) as exc:
            self.state = str(exc)
            self.render_comparison()
            return
        self.dismiss(dict(model=model, gpus=resources['gpus'], minimum_vram=self.minimum))

    def on_button_pressed(self, event):
        event.stop()
        if event.button.id == 'run-compare':
            self.action_compare()
        elif event.button.id == 'use-model':
            self.action_use()
        elif event.button.id == 'compare-back':
            self.key_escape()

    def key_escape(self):
        if isinstance(self.focused, Input):
            self.query_one('#comparison').focus()
        else:
            self.dismiss(dict(minimum_vram=self.minimum))


class HendrixApp(App):
    TITLE = 'Hendrix'
    SUB_TITLE = 'Local projects · Slurm GPUs · jobs'
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
    #dialog #run-name-row { height: 1; }
    #run-name-label { width: 11; }
    #run-name { height: 1; border: none; padding: 0; width: 1fr; }
    #run-name:focus { background: $surface; }
    #submit-gpus { height: 10; min-height: 5; margin-bottom: 1; }
    #dialog.launch-dialog { padding: 0 1; }
    #dialog.launch-dialog #launch-buttons { height: 1; }
    #dialog.launch-dialog #launch-buttons Button { height: 1; border: none; padding: 0 1; }
    #dialog.launch-dialog Static, #dialog.launch-dialog Label,
    #dialog.launch-dialog Input, #dialog.launch-dialog Select,
    #dialog.launch-dialog #submit-gpus { margin-bottom: 0; }
    #advanced { height: auto; padding: 0; margin-bottom: 1; }
    #dialog.comparison-dialog { width: 120; padding: 0 1; }
    #dialog.comparison-dialog Static, #dialog.comparison-dialog Input,
    #dialog.comparison-dialog Label { margin-bottom: 0; }
    #comparison { height: 10; min-height: 4; border: round $border; }
    #form-error { color: $error; }
    .dialog-title { color: $primary; text-style: bold; }
    .muted { color: $foreground-muted; }
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
                Binding('alt+l', 'next_tab', 'Next tab', show=False),
                Binding('1', 'section(1)', 'Models', show=False),
                Binding('2', 'section(2)', 'Nodes', show=False),
                Binding('3', 'section(3)', 'Projects', show=False),
                Binding('4', 'section(4)', 'Jobs', show=False),
                Binding('5', 'section(5)', 'Logs', show=False),
                Binding('6', 'section(6)', 'Cluster queue', show=False)]

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
        self.jobs_view = 'recent'
        self.jobs_limit = 3
        self.cluster_jobs = None
        self.queue_warning = ''
        self.data_errors = {}
        self.queue_partition = 'gpu'
        self.old_jobs = {}
        self.last_gpu = self.last_history = self.last_jobs = self.last_queue = 0
        self.last_gpu_at = self.last_queue_at = None
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
            with TabPane('3 Projects', id='project-tab'):
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
                    yield Button('Save login password', id='password')
                    yield Button('Setup SSH key', id='setup-key')
                yield NavigationLog(id='sync-output', wrap=True, markup=False, max_lines=1000)
            with TabPane('4/5 Jobs / Logs', id='jobs-tab'):
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
                             ('jobs', '4 · Jobs'), ('job-log', '5 · Logs')]:
            self.query_one('#' + ident).border_title = title
        self.render_nodes()
        self.render_cluster_queue()
        self.render_jobs()
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
        self.selected_model = None
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
        if event.data_table.id == 'models':
            self.selected_model = str(event.row_key.value)
            self.notify(f'Next submission GPU: {self.selected_model}')
        elif event.data_table.id == 'jobs':
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
            state_style = theme_color("red") if not n['eligible'] else theme_color("green") if n['state'] == 'IDLE' else theme_color("yellow")
            cells = [Text(name + (' ●' if marked else ''),
                          style=("bold " + theme_color("accent")) if marked else theme_color("text")), model,
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
        table.border_title = '2 · GPU nodes · free(total)'
        table.border_subtitle = 'v mark · y copy · b run'
        models.clear(columns=True)
        for key, label, width in [('model', 'Model', 12), ('gpu', 'GPU', 10), ('cpu', 'CPU', 13), ('ram', 'Host RAM GiB', 16),
                                  ('vram', 'VRAM/GPU', 12), ('healthy', 'Healthy free', 12),
                                  ('pending', 'Pending tasks', 16)]:
            models.add_column(self.header_label(key, label), key=key, width=width)
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
            models.add_row(Text(row['model'] + (' ●' if marked else ''), style=("bold " + theme_color("accent"))), self.resource_text(gpu, row['total']),
                           self.resource_text(cpu_free, cpu_total), self.resource_text(ram_free, ram_total, gib=True),
                           core.gpu_metadata(row['model'])['vram'], '?' if row['usable_unknown'] else str(row['usable']),
                           ('?' if demand is None or demand.get(row['model'], {}).get('unknown') else
                            str(demand.get(row['model'], {}).get('tasks', 0))),
                           key=row['model'])
            if row['model'] == previous_model:
                models.move_cursor(row=index, scroll=False)
        models.styles.height = min(12, max(4, len(totals) + 3))
        models.border_title = '1 · GPU models · free(total)'
        models.border_subtitle = 'v mark · b run · Click heading to sort'
        total = sum(len(n['capacity']) for n in self.nodes)
        self.query_one('#gpu-view-status', Static).update(
            f'{len(rows)}/{total} rows · {len(self.marked_rows)} marked · '
            + ('model preference' if self.sort_key == 'preference' else self.sort_key + (' ↓' if self.sort_reverse else ' ↑')))
        self.query_one('#gpu-advice', Static).update(
            f'Visible pending demand ({self.queue_partition if self.queue_partition != "*" else "all visible"}): '
            + ('unavailable' if demand is None else 'Any GPU: ' + core.demand_text(demand.get('any')))
            + f' · {self.queue_freshness()}\nInventory: {core.display_time(self.last_gpu_at)} · '
              'Nominal VRAM; variants/aliases may be uncertain. Host RAM is separate.')

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
                        3: ('project-tab', 'sync'), 4: ('jobs-tab', 'jobs'),
                        5: ('jobs-tab', 'job-log'), 6: ('queue-tab', 'cluster-queue')}[section]
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
        panes = ['gpu-tab', 'project-tab', 'jobs-tab', 'queue-tab']
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
        # Recreate auto-sized columns so removed rows cannot leave oversized
        # widths behind. Textual measures just the headers and current rows.
        table.add_columns('Job', 'Project', 'Run', 'State', 'Elapsed', 'Limit',
                          'Node / reason', 'GPU', 'Exit')
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
            table.add_row(job['id'], record.get('project', '—'), run_name or job['name'],
                          job['state'], job['elapsed'], job['limit'], job['reason'],
                          core.compact_job_gpu(job['gpu']), job.get('exit', ''), key=job['id'])
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
        for key, label, width in [('id', 'Job / array', 27), ('gpu', 'GPU request', 27),
                                  ('tasks', 'Tasks / cap', 16), ('cpus', 'CPUs/job', 9),
                                  ('memory', 'Host RAM min', 16), ('limit', 'Limit', 13),
                                  ('reason', 'Reason (raw)', 27), ('submitted', 'Submitted (local)', 22),
                                  ('start', 'Scheduler start (local)', 22), ('partition', 'Partition', 22)]:
            table.add_column(label, key=key, width=width)
        search = self.query_one('#queue-filter', Input).value.lower()
        visible = [j for j in self.cluster_jobs or [] if core.in_partition(j, self.queue_partition)]
        rows = [j for j in visible if not search or search in ' '.join(
            str(j[key]) for key in ('id', 'gpu', 'reason', 'explanation', 'partition', 'category')).lower()]
        rows.sort(key=lambda j: (j['submitted'] is None, j['submitted'] or dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc), j['id']))
        for index, job in enumerate(rows):
            tasks = str(job['tasks']) if job['tasks'] is not None else '?'
            cap = core.cap_text(job)
            table.add_row(job['id'], job['gpu'], f'{tasks} / {cap}', job['cpus'], job['memory'], job['limit'],
                          job['reason'], core.display_time(job['submitted']), core.display_time(job['start']),
                          job['partition'], key=job['id'])
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
    async def action_submit(self):
        if self.busy or isinstance(self.screen, ModalScreen):
            return
        if not self.profile.presets:
            self.notify('Add a batch-script preset using Edit profiles first.', severity='warning')
            return
        self.busy = True
        try:
            models = sorted({model for n in self.nodes for model in n['capacity']})
            selected = list(request_groups(self.nodes, self.marked_rows)) if self.marked_rows else []
            if not selected and isinstance(self.focused, DataTable) and self.focused.id in ('models', 'nodes'):
                selected = list(self.copy_groups())
            inventory = {r['model']: (None if r['unknown'] else r['unallocated'], r['total'],
                         max(n['capacity'].get(r['model'], 0) for n in self.nodes))
                         for r in summarize(self.nodes)}
            freshness = ('Inventory updated ' + core.display_time(self.last_gpu_at)
                         + (' · stale: ' + self.data_errors['inventory'] if 'inventory' in self.data_errors else '')
                         + '\n' + self.queue_freshness())
            form = SubmitForm(self.profile, models, self.selected_model, selected, inventory,
                              self.backend, self.nodes, self.cluster_jobs, freshness)
            request = await self.push_screen_wait(form)
            if request is None:
                return
            preset, requests = request
            summary = (f'Sync project source and submit {len(requests)} job(s)?\n\n'
                       f'{self.profile.name} → {self.profile.host}\n'
                       f'Run name: {form.run_name}--GPU_MODEL\n'
                       f'Batch script: {shlex.join([preset["script"], *preset.get("args", [])])}\n'
                       + '\n\n'.join(f'Job {i}: ' + ', '.join(f'{key}: {value}' for key, value in resources.items())
                                        for i, resources in enumerate(requests, 1)) +
                       (f'\n\nAdvisory minimum VRAM: {form.minimum_vram} nominal GB/GPU (not a Slurm flag).'
                        if form.minimum_vram else '') +
                       '\n\nEach GPU model runs the script separately, with its own snapshot and logs.' +
                       '\n\nDatasets and the existing environment remain shared. Jobs may queue. No GPU fallback.')
            if not await self.push_screen_wait(Confirm(summary)):
                return
            core.remember_launch(self.profile, preset, requests, form.minimum_vram)
            for i, resources in enumerate(requests, 1):
                self.output(f'Preparing job {i}/{len(requests)}: {resources["model"]} × {resources["gpus"]}…')
                try:
                    result = await asyncio.to_thread(self.backend.submit, preset, resources, run_name=form.run_name)
                except (Error, OSError, ValueError, subprocess.SubprocessError):
                    self.output(f'Stopped at job {i}/{len(requests)}. Earlier submitted jobs remain active; '
                                'remaining requests were not attempted. Reconcile if the response was lost.')
                    raise
                self.output(f'Submitted job {result["job_id"]}\nSnapshot: {result["snapshot"]}\nLogs: {result["output"]}')
                self.notify('Submitted job ' + result['job_id'])
            self.show_profile()
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
