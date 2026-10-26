# Hendrix from your PC

Start with `hendrix tui`. It brings up/reuses the KU VPN, authenticates SSH, and
loads GPU availability automatically. Sudo/MFA prompts appear before the TUI.
A helper tunnel with unavailable DNS gets a five-second recovery window, then
one clean down/up attempt. Login failure or cancellation leaves the app open;
press **c** to retry. Background polling never prompts for credentials.

The app runs locally using SSH, rsync and Slurm commands. The project launcher
has been removed from the TUI; use your own batch/Python scripts for runs.
GPU request copying, job monitoring, logs and confirmed cancellation remain.

## Login

```bash
hendrix password set   # Type your KUnet password into the desktop keyring
hendrix up             # Reuse KU network or log in (optional automatic TOTP below)
hendrix setup-ssh      # Optional: installs your configured public key into your own remote account
hendrix connect        # Open/reuse an authenticated SSH connection
hendrix tui
```

`hendrix password set` saves the KUnet password used for **both VPN and Hendrix
SSH** on this PC. It can update an expired password. `hendrix password forget`
removes it; subsequent logins ask interactively. Passwords and VPN cookies are
passed through private pipes, never saved in the repository, Nix store, command arguments
or job history. The saved password is attempted only
once per connection; if it fails, SSH asks you to type a password in the terminal.
Keyring integration is desktop-only; the shared app also works on
the mobile VPS if the KU network is reachable separately.

### Optional automatic authenticator codes

`hendrix totp set` accepts a hidden Base32 authenticator setup key or an
`otpauth://totp/…` URI. Alternatively, import a local authenticator QR image:

```sh
hendrix totp import /absolute/path/to/authenticator-qr.png
hendrix totp status
hendrix connect
```

Use the enrollment QR/setup key for the same account that currently supplies
your VPN codes. NetIQ enrollment links that are not ordinary `otpauth` TOTP
provisioning are unsupported. SHA1, six digits and a 30-second period are
required; other settings are rejected rather than silently misinterpreted.
Do not put the secret itself in command arguments, shell history or dotfiles.
Delete any temporary QR image after importing it; the image contains the
authenticator secret.

The seed is saved separately from the password in the desktop Secret Service
keyring. OpenConnect generates the current code when the VPN requests it,
using an inherited anonymous RAM file; the seed is never included in command
arguments, environment variables, the Nix store or persistent helper files.
It is accessed only when explicitly starting a new VPN login. Background TUI
refreshes and SSH password authentication do not read it. Without an available
saved seed, MFA remains interactive. Authentication failures are not retried
automatically. `hendrix totp forget` returns to entering codes manually.

Keeping both credentials on this PC reduces MFA's protection if the PC or
unlocked keyring is compromised. It does not require browser access, and it
does not upload the authenticator seed to the VPS.

SSH key setup preserves existing keys and uses the first configured identity with
a matching `.pub` file. Encrypted keys may need `ssh-add`. If the server declines
key authentication, `hendrix tui`, **c / Connect**, `hendrix connect`, and `hendrix ssh` use the
saved password through OpenSSH's private askpass pipe. Keys and an existing SSH
session take precedence. The shared password is only supplied to the configured
`fhz806@hendrixgate` account; unexpected hosts, accounts, key-passphrase and MFA
prompts cannot consume it. A rejected or timed-out saved-password login falls back
to one manual password attempt. A locked/unavailable keyring also falls back to
interactive login after a bounded wait. Typing a password here does not replace
the keyring entry; use `hendrix password set` to update it. Background refreshes do not read the keyring or authenticate
with the password; reconnect explicitly with **c** when needed. The app's SSH/sync
commands reuse the authenticated connection, which stays alive for 15 minutes
after its last use. `hendrix ssh` uses the same connection. Plain `ssh hendrix`
continues to use your existing SSH configuration.

On a new direct desktop connection, the tool checks the gateways returned by
Hendrix DNS in parallel for an SSH greeting, allowing up to five seconds. It then
connects through the first responding gateway while retaining the configured SSH
hostname and account. This avoids a gateway that accepts TCP but stalls before
authentication. No responding gateway produces a network error before any password
attempt. Custom SSH proxies, jump hosts and other accounts retain their configured
transport. An existing authenticated connection is reused without gateway probes.
Login errors and **Ctrl+C** restore the TUI instead of leaving the terminal suspended;
press **c** to try again. VPN connectivity alone does not prove SSH is available.

The desktop uses `systemd-resolved` to route DNS separately for Wi-Fi, the KU VPN,
and Tailscale. OpenConnect registers the KU DNS servers and search domains on
`hendrix0`; Tailscale registers MagicDNS on `tailscale0`. The helper leaves
Tailscale DNS enabled, so Obsidian can reach the mobile VPS while Hendrix is in use.
The desktop NixOS configuration enables this setup through `nxb`.
It also routes `tail55f864.ts.net` directly to Tailscale's local MagicDNS
resolver (`100.100.100.100`). This takes precedence over the tailnet's broader
`ts.net` route to public DNS, which cannot resolve private device names.
If the hub or `/codex/` fails, compare `resolvectl query
mobile-dev.tail55f864.ts.net` with `sudo tailscale dns query
mobile-dev.tail55f864.ts.net`: an internal answer with a failed system lookup
indicates DNS routing rather than a stopped VPS service.

`hendrix down` stops only the VPN started by this helper and removes its per-link
DNS settings. Batch jobs continue running. Quit the TUI with **q**;
quitting does not disconnect the VPN or cancel jobs.

After VPN authentication, the helper allows up to 20 seconds for Hendrix DNS to
become available. If that fails, it disconnects and cleans up before reporting
the error. A DNS failure alone does not establish that the cluster is down.
Tunnel diagnostics are available with `journalctl -t openconnect`.

## Remote terminal setup

Run `hendrix shell-setup` on the PC once, then open a new session with
`hendrix ssh`. This installs Ghostty's terminal definition and a pinned static
zoxide binary in your own cluster account. Existing shell startup files are
preserved, with backups under `~/.config/hendrix/backups/` before adding hooks.
The setup is repeatable and only affects interactive Bash sessions.

The prompt puts input on a separate line. **Tab / Shift+Tab** cycle completions;
**Up / Down** search history matching the text already typed. Pasted multiline
text stays editable before execution. Existing Bash completion is loaded.

`cd mean` jumps to the registered MeanFlow project from anywhere. Ordinary
`cd path`, `cd ..` and `cd -` still work. Visiting other directories teaches
zoxide more destinations; `cd keyword` then finds them. No directory is moved
or renamed, and submitted Slurm jobs keep running through reconnection.

## GPU numbers

The GPU tab defaults to **Healthy + free GPUs**: IDLE/MIXED nodes with
known free GPUs, excluding unavailable state flags. Switch the state dropdown to
healthy nodes, all nodes, IDLE, MIXED, ALLOCATED or unavailable nodes. The model
totals and node rows follow both this dropdown and the text filter. Unknown GPU
allocations are visible with the broader filters. Filtering uses cached data and
makes no additional Slurm requests.

Press **1** for GPU models, **2** for GPU nodes, **3** for Jobs, **4** for
Logs, **5** for Projects, and **6** for the Cluster queue. Numbers appear on the tabs and panel borders.
Use **hjkl** as table arrows (j/k move rows; h/l scroll horizontally), **g/G** for
the first/last row, **Ctrl+d/u** to page down/up, **Tab / Shift+Tab** to move
between controls, and **Alt+h / Alt+l** to change tabs. In dropdowns, j/k open
and move through choices; Enter selects. In text fields, hjkl type normally.
**Shift+L** opens job logs. Refreshes retain the selected table row when possible.

Default sorting uses a browsing preference: H100, A100, L40S, A40, RTX models,
then older Titans and unknown models. It is not a measured performance ranking.
Within a model, known free capacity comes first; unavailable nodes come last.
Click a Model, GPU, CPU, RAM, Node or State heading to sort; click again to reverse.
Press **=** to restore the default preference. There is no separate sort dropdown. More host RAM/CPUs
does not imply a faster GPU: GPU memory fit, actual workload performance and queue
wait matter. The app does not benchmark training speed. Click **Pending tasks**
to sort by visible pending demand (unknown counts remain last).

Both GPU tables show an eight-character bar for the free share, beside exact
**free(total)** counts. A full green bar means all GPUs are unallocated, an empty
bar means none are free, and question marks mean allocation data is unknown.
These describe Slurm allocations, not measured GPU utilisation.

The default tables are compact. Press **Shift+C / Columns** (or click Columns)
to choose optional columns separately for models, nodes, jobs and the cluster
queue. Space toggles a column; **Compact** and **All columns** provide presets.
**Save** persists all choices to `~/.config/hendrix/ui.json`; **Back / Esc**
discards edits. Identity columns remain visible. CPU/RAM, pending demand and
other details are available through this chooser. Reasons still has its own toggle.

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

Use **v** to mark/unmark node rows or all rows for the focused GPU model, and
**Shift+V** to clear marks. **y** copies a
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
VRAM variant. The model overview adds nominal VRAM per GPU, healthy unallocated
capacity, and pending tasks for the partition selected in Cluster queue. Its
capacity totals still follow the GPU search/state filter; pending demand is for
the whole selected partition. Any GPU demand appears separately above the table.
Scroll horizontally with h/l for extra columns on narrow terminals.

## Cluster queue

**6 · Cluster queue** defaults to `gpu`. Choose another inventoried/visible
partition or **All visible partitions**. Search with **/**; **Esc** returns to
the table. Refresh/filtering preserves the selected row when it remains visible.
The table shows job/array ID, GPU request scope, pending task count and concurrency
cap, CPUs per job, minimum host RAM per CPU/node, time limit, raw pending reason,
submission time and scheduler start estimate. Both timestamps use your PC's local
timezone. Select a row to read its full details below the horizontally scrolling
table. Arrays are counted from compact ranges, including stepped ranges and `%`
caps; truncated, overlapping or unsupported ranges show `?`, with known partial
counts identified. A missing cap for a materialized array task is unknown.

Summary counts mean **visible pending demand**, not your queue position. Resources
and Priority are waiting; dependencies, holds, array concurrency caps and future
starts are blocked; other reasons retain their raw explanation. Blocked tasks
are included and separated, not treated as immediately competing jobs. Jobs
requesting an unspecified model stay in **Any GPU** and are never counted against
every GPU model. Jobs with no GPU reported have their own group. Multi-partition
jobs are counted once in the all-partitions view. Restricted jobs may be hidden
by cluster policy. Queue freshness, query failures and partial parsing appear
above the table. Filters use the cached bulk query and make no SSH calls.

Queue inspection uses one cached `scontrol show jobs -o` query with
`SLURM_BITSTR_LEN=4096`, not a query per array task. Timestamps use your PC's
local timezone. GPU comparisons and submission forms were removed with the
project launcher; choose requests and submit through your own scripts.

## Projects and existing snapshots

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
The TUI no longer submits projects or creates snapshots. Existing snapshots and
submission history are retained so old jobs can still be monitored or reconciled.

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

The Jobs tab loads your active jobs and the past week of accounting history.
The recent-finished count accepts `0` to hide
finished jobs, a positive count to limit them, or `-1` to show all loaded history.
Job columns size themselves to the visible rows and shrink when longer rows are
removed or hidden, keeping the table compact in a narrow terminal.
**Shift+L / Logs** or Enter on a job displays its latest 150 lines. Once logs are
open, selecting another job switches the log view. **Follow** refreshes the
selected job's bounded tail every 10 seconds while connected; turning it off
pauses refreshes and still lets you switch between jobs.
Resolved log paths are retained when a job leaves Slurm's live records. For jobs
submitted outside the TUI, completed-job logs can also be found in the selected
project root or directly inside its `results/runs/*/` directories, using names
such as `slurm-628_3.out` and `slurm-628_3.err`.
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

## Other cluster workflows

These workflows use **SSH and batch scripts** (`t / SSH` or `hendrix ssh`); the
TUI currently provides advisory queue/comparison views, ordinary batch submission,
monitoring, cancellation, bounded logs, sync/snapshots and result downloads.
New array/dependency controls, automatic selection and benchmark execution are
outside this upgrade. The examples below are commands to run yourself.

**Batch jobs** enter the queue immediately and survive disconnects:

```bash
sbatch --partition=gpu --gres=gpu:l40s:1 --cpus-per-task=4 --mem=32G --time=05:00:00 train.sbatch configs/hendrix_b4.yml
squeue -u "$USER"
scontrol show job JOB_ID
```

**Interactive work** uses an allocation, then a shell on its compute resources:

```bash
salloc --partition=gpu --gres=gpu:l40s:1 --cpus-per-task=4 --mem=32G --time=01:00:00
srun --pty bash
hostname
nvidia-smi
```

Interactive shells require a maintained session (for example tmux on the login
host, if available). Exit the compute shell and allocation when finished. Put
long unattended training in a batch script so losing SSH does not lose your shell.
Do training on allocated compute resources, and use the login host for setup and
scheduler/file operations.

**Arrays**, dependencies, holds and future starts remain script/SSH controls:

```bash
sbatch --array=0-9%2 --output='array-%A_%a.out' sweep.sbatch
sbatch --dependency=afterok:JOB_ID evaluate.sbatch
sbatch --dependency=afterany:JOB_ID cleanup.sbatch
sbatch --hold train.sbatch
scontrol hold JOB_ID
scontrol release JOB_ID
sbatch --begin=now+1hour train.sbatch
```

An array script uses `SLURM_ARRAY_TASK_ID` to choose its configuration. The `%2`
cap limits simultaneous tasks; each task has the script's full resource request.
`afterok` waits for success, `afterany` waits for completion regardless of status.
A failed dependency can remain pending. Holds and requested future starts are
separate from resource/priority waiting. A future start is an eligibility time,
not a guaranteed dispatch time. Keep these directives in your own batch scripts
and review them together with the requested resources.

**Monitoring/accounting and cancellation**:

```bash
squeue -u "$USER"
squeue --start -u "$USER"
sacct -X -j JOB_ID --format=JobID,State,Elapsed,Timelimit,AllocTRES,ExitCode
sstat -j JOB_ID.batch --format=JobID,MaxRSS,AveCPU
scancel JOB_ID
scancel ARRAY_ID_TASK_ID
```

Accounting/step metrics depend on the site's retention and configuration. Inspect
exit status as well as logs. The TUI's cancellation requires confirmation; an SSH
`scancel` acts immediately. Cancelling a base array ID cancels its remaining tasks.
Use `tail -f` over SSH for a continuous log, or TUI Follow for a bounded tail;
output paths are defined by your script or the TUI's submission record.

**Modules, environments, files and storage**:

```bash
module avail
module load MODULE_NAME
source .venv-hendrix/bin/activate
df -h .
quota -s                        # If the site provides quota reporting
```

Place the appropriate module/environment setup in your script. Keep packages in
the project environment; the TUI reuses it and does not install dependencies.
From the PC use `scp` or `rsync` with your existing SSH access for datasets,
environments and custom results. Inspect transfer destinations and storage
capacity; large shared data is intentionally excluded from TUI source sync.
Preview and Sync update the owned mirror, while Submit uses a retained snapshot;
transfer datasets to the existing remote shared directories separately.

**Notebooks and tunnels** need an interactive allocation and manual SSH setup.
On the allocated compute node run, with Jupyter installed in your environment:

```bash
jupyter lab --no-browser --ip=127.0.0.1 --port=8888
```

Where the cluster permits SSH to your allocated node, open a separate PC terminal
and forward to its loopback address through the login host:

```bash
ssh -J hendrix -L 8888:127.0.0.1:8888 USER@ALLOCATED_NODE -N
```

Open the token URL at `http://127.0.0.1:8888` on the PC. If compute-node SSH is
restricted, use the site's approved relay/tunnel procedure. Forwarding directly
from the login host to a compute node's external address cannot reach a notebook
bound only to compute loopback. Keep the allocation and tunnel alive; stop the
notebook and release resources afterwards. The TUI does not create tunnels.

## Validation

Offline tests use disposable local directories, a fake `sbatch`, and mocked SSH
responses. They do not log in or allocate any cluster resources:

```bash
PYTHONPATH=scripts python -m unittest discover -s tests -p test_hendrix.py -v
```

Run with the Textual-enabled Python provided by the Nix package. The package and
VPN helper are activated with the normal `nxb` rebuild.

## Keeping the Jobs view readable

Jobs defaults to **Active + recent finished**, showing every active job and the
three most recently finished jobs. Change the view to **Active only**, **Recent
finished**, **Completed only**, or **All jobs**. Set the recent count to any
nonnegative number; **0** hides finished jobs; **-1** shows all finished jobs in the loaded history. Recent
finished includes failures/cancellations so a failed latest run stays visible.
Active jobs are shown first; finished jobs use Slurm completion time when known.
Filtering uses cached data and does not cancel, delete, or query jobs separately.
The existing accounting query loads the last seven days of history.

The table separates **Project** from **Run / preset** and shows compact GPU
requests instead of long accounting TRES strings. Existing registered jobs get
preset labels from their saved script/arguments even if their old Slurm names
were generic.

Existing registered jobs retain their saved run names. New jobs submitted with
your own scripts display their Slurm job names.
