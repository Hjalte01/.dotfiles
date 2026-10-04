# Hendrix from your PC

Start with `hendrix tui`. Opening the app makes no connection; press **c** when
ready to log in. The app runs locally and uses standard SSH, rsync and Slurm
commands. It installs no services or agents on the cluster, does not probe compute
nodes directly, and only submits or cancels jobs after you confirm an action.

## Login

```bash
hendrix password set   # Type your KUnet password into the desktop keyring
hendrix up             # Existing KU network is reused; new VPN sessions ask for NetIQ MFA
hendrix setup-ssh      # Optional: installs your configured public key into your own remote account
hendrix connect        # Open/reuse an authenticated SSH connection
hendrix tui
```

`hendrix password set` can update an expired password. `hendrix password forget`
removes it; subsequent VPN logins ask interactively. Passwords and VPN cookies are
passed through stdin, never saved in the repository, Nix store, command arguments
or job history. The MFA seed is not stored. A failed login is not retried
automatically. Keyring integration is desktop-only; the shared app also works on
the mobile VPS if the KU network is reachable separately.

SSH key setup preserves existing keys and uses the first configured identity with
a matching `.pub` file. Encrypted keys may need `ssh-add`. If the server declines
key authentication, use `hendrix connect` with your password: the app's SSH/sync
commands reuse the authenticated connection, which stays alive for 15 minutes
after its last use. `hendrix ssh` uses the same connection. Plain `ssh hendrix`
continues to use your existing SSH configuration.

`hendrix down` stops only the VPN started by this helper and restores the previous
Tailscale DNS preference. Batch jobs continue running. Quit the TUI with **q**;
quitting does not disconnect the VPN or cancel jobs.

After VPN authentication, the helper allows up to 20 seconds for Hendrix DNS to
become available. If that fails, it disconnects and cleans up before reporting
the error. A DNS failure alone does not establish that the cluster is down.
Tunnel diagnostics are available with `journalctl -t openconnect`.

## GPU numbers

The GPU tab defaults to **Healthy + free GPUs**: IDLE/MIXED nodes with
known free GPUs, excluding unavailable state flags. Switch the state dropdown to
healthy nodes, all nodes, IDLE, MIXED, ALLOCATED or unavailable nodes. The model
totals and node rows follow both this dropdown and the text filter. Unknown GPU
allocations are visible with the broader filters. Filtering uses cached data and
makes no additional Slurm requests.

Use **hjkl** as table arrows (j/k move rows; h/l scroll horizontally), **Tab** to
move between controls, and **Alt+h / Alt+l** to change tabs. In dropdowns, j/k open
and move through choices; Enter selects. In text fields, hjkl type normally.
**Shift+L** opens job logs. Refreshes retain the selected table row when possible.

Default sorting uses a browsing preference: H100, A100, L40S, A40, RTX models,
then older Titans and unknown models. It is not a measured performance ranking.
Within a model, known free capacity comes first; unavailable nodes come last.
Click a Model, GPU, CPU, RAM, Node or State heading to sort; click again to reverse.
Press **=** to restore the default preference. There is no separate sort dropdown. More host RAM/CPUs
does not imply a faster GPU: GPU memory fit, actual workload performance and queue
wait matter. The app does not benchmark or estimate wait times.

Both tables use **free(total)**: `4(6)` means four unallocated GPUs out of six.
CPU counts show effective CPUs minus allocated CPUs. RAM counts show configured
host RAM minus Slurm-allocated RAM, in GiB. `?` means Slurm did not supply a known
allocation. These are reservations, not measured utilisation or operating-system
free memory. CPU/RAM belong to the whole node and are shared by its GPUs. For
nodes with multiple GPU models, those same CPU/RAM resources appear alongside
each model; model totals cannot be combined into one job allocation.

Search sits above both tables, and summary totals follow the search and state
filter. On narrow terminals, display names omit the `hendrix` prefix; copied
requests always preserve the full hostname. The **Reasons off (N)** button counts
visible nodes with a reason and optionally shows that column; it starts hidden.
Press **R** to toggle it. More details are under **? / Help**.

Use **v** to mark/unmark node rows and **Shift+V** to clear marks. **y** copies a
one-GPU request such as `#SBATCH --gres=gpu:a100:1` for marked rows, or the focused
node/model if nothing is marked. Slurm chooses the node. Several marked nodes do
not request several GPUs. Mixed-model selections open a chooser because GRES
model names are not an OR-list. **Shift+Y** reviews the request and offers pinning
one exact node when only one node is selected for that model; this may increase
queue wait. The latest request is also saved in
`~/.local/state/hendrix/copied-request.json`. Marking and copying are local actions
and do not submit jobs or reserve resources.

Unallocated GPUs are not guaranteed immediately schedulable: CPU/RAM requirements,
reservations, account/group restrictions and scheduler priorities still apply.
Nodes in down, drained or other unavailable states are excluded from usable-node
counts. The app does not infer your access to research-group partitions; use the
ordinary `gpu` partition unless you have been granted another one.

Slurm need not fill one node before using another. CPU/RAM requirements, GPU
models, reservations and scheduling policy affect placement; a free GPU does
not imply the node can fit another job. Spread jobs can have more CPU/RAM resources
per GPU, but the app does not infer Hendrix's scheduling policy from counts.

Host RAM is separate from GPU VRAM. GPU model names do not necessarily identify a
VRAM variant. Select a model row to prefill the next submission, or type the exact
Slurm GRES model name in the submission form. Default: `gpu` partition, one
`a100`, four CPUs and 32 GB host RAM. `any` requests an unspecified GPU. There is
no silent fallback to another GPU model. The GPU count field is limited to 1–8;
Slurm still enforces actual permissions and limits. Compare queue wait plus run
time when deciding between models; no benchmark or automatic GPU ranking is
performed by the tool.

Jobs refresh every 30 seconds and GPU inventory every 60 seconds. Manual refresh
is **r**. Connection failures mark data stale and pause polling until you reconnect
or manually refresh. Finished-job accounting is queried every 60 seconds over the
last two days. Pending reason and elapsed runtime are different from queue wait;
elapsed runtime is not an estimated completion time.

## Projects and snapshots

Profiles live in `~/.config/hendrix/profiles.json`; local history and submission
manifests live in `~/.local/state/hendrix/`. XDG environment overrides are honored.
The MeanFlow profile is seeded only when the profile file does not exist. Use
**Add project**, **Edit profiles**, or `hendrix profiles` to manage multiple repos.

Each project saves its SSH alias, local/remote root, exclusions, shared paths,
environment path, and batch presets. For example:

```json
{
  "name": "MeanFlow",
  "local": "/absolute/local/repo",
  "remote": "~/projects/ATDL-MeanFlow-Reproduction",
  "host": "hendrix",
  "excludes": [".git/", ".venv*/", "__pycache__/", "data/", "*.out"],
  "shared": ["data", "datasets", "checkpoints", "results"],
  "venv": ".venv-hendrix",
  "presets": [
    {"name": "Smoke", "script": "scripts/hendrix/smoke.sbatch", "args": [], "time": "00:30:00"},
    {"name": "Train", "script": "scripts/hendrix/train.sbatch", "args": ["configs/hendrix_b4.yml"], "time": "05:00:00"}
  ]
}
```

The file wraps profiles in `{"version": 1, "projects": [...]}`. Paths for scripts,
shared directories and environments are project-relative. Use absolute cluster
paths for dataset/checkpoint locations in training YAML. Supply any necessary
module/environment setup in the batch script or the environment established by
your SSH login; the TUI does not configure the cluster environment for you.

- **p / Preview:** show incremental changes without modifying remote files.
- **s / Sync:** update only the tool-owned `.hendrix/source` mirror. Removed source
  files are removed from this mirror; existing datasets/environments/results are
  protected. Large shared directories and `.hendrix/` are always excluded.
- **b / Submit:** review the script and resource request, sync first, copy source
  into a unique `.hendrix/snapshots/TOKEN` directory, and submit from that snapshot.
  Shared directories are symlinks to the existing remote project. `MEANFLOW_VENV`
  points at the existing environment. Later syncs cannot change the snapshot.

Do not manually sync into snapshot directories. Snapshots are retained for
reproducibility; the app does not automatically delete remote history. Jobs you
submit manually from the old project root continue to use that root, which the
TUI's source sync does not overwrite. Setup/dataset preparation remains a separate
step; changing dependencies requires updating the shared environment before use.

Batch logs are saved under `results/runs/hendrix-TOKEN/slurm-JOB.out` and `.err`.
The MeanFlow scripts retain their own shared `results/runs/smoke-JOB` and
`train-JOB` outputs. Job history records the project, script, args, resource request,
snapshot, token, log directory and returned job ID. Source snapshots preserve
uncommitted edits as well as committed code.

## Jobs, logs and lost submission responses

The Jobs tab shows your jobs. **Shift+L / Logs** displays the latest 150 lines;
**Follow** refreshes this bounded tail every 10 seconds while connected.
**stderr** switches streams. Cancellation requires confirmation.
**Download results** copies logs and, for the seeded MeanFlow presets, the full
run output (including potentially large checkpoints) into the owning local
project's `results/runs/hendrix-JOB/`. For other scripts, the default download
includes logs; use your own rsync profile/command for custom output locations.

If SSH drops during `sbatch`, the job may already have been accepted. The app
records the attempt and blocks further submissions for that project rather than
risking a duplicate. Use **Reconcile** (or `hendrix reconcile`) to search your jobs
for the unique Slurm comment. If it cannot find the job, absence is not proof it
was rejected. After checking queue/accounting, resolve explicitly:

```bash
hendrix --project MeanFlow resolve TOKEN --job-id JOB_ID
# Only if you have confirmed that Slurm did not accept the attempt:
hendrix --project MeanFlow resolve TOKEN --not-submitted
```

The second command requires typing the token to confirm. Automatic reconciliation
covers the last two days and depends on Slurm retaining job comments in accounting.
No submission is automatically retried.

## Validation

Offline tests use disposable local directories, a fake `sbatch`, and mocked SSH
responses. They do not log in or allocate any cluster resources:

```bash
PYTHONPATH=scripts python -m unittest discover -s tests -p test_hendrix.py -v
```

Run with the Textual-enabled Python provided by the Nix package. The package and
VPN helper are activated with the normal `nxb` rebuild.
