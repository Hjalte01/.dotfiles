# Device comparer

Run `devices` from Bash to open the terminal comparer. It opens saved data
immediately and makes no network connections until you refresh a Linux host.
With redirected output, `devices` prints a text comparison instead.

- Arrow keys or `j`/`k`: select a device; `h`/`l`: move through the wide table.
- `Tab`: move between the table and scrollable device details.
- `r`: refresh selected Linux host. `Ctrl+r`: reload saved inventory.
- `f`: enter job RAM, CPU, disk, architecture and CUDA requirements.
- `a`: add a device, leaving unknown specs empty.
- `?`: help. `q`: quit.

## Devices and confidence

The main PC and `mobile-dev` VPS have measured Linux hardware. The VPS has
2 shared vCPUs, approximately 3.73 GiB of usable RAM, and no swap. Its Virtio
GPU is a display device. The main PC has a Ryzen 7 7735U with 8 cores/16
threads and integrated Radeon 680M graphics. RAM values are OS-usable,
which can be smaller than the installed capacity.

The iPhone 11 Pro has Apple A13 specifications, with unknown owned storage
capacity and unverified RAM. The owner recalls a 2025 11-inch iPad Air,
so M3 is a possibility; its chip, RAM and storage remain unconfirmed until
the model number is checked in Settings → General → About. Apple source
links and model-number guidance are saved with these devices.

Stock iOS/iPadOS devices are clients for SSH and web apps here. The resource
checker evaluates Linux job placement; it does not evaluate native mobile apps.

## Readable output for Codex

```bash
devices list
devices show mobile-dev
devices --json
devices refresh all
devices check --ram 2 --cpus 2 --disk 5
devices check --device mobile-dev --ram 1 --cpus 1 --disk 2 --json
devices check --ram 8 --cuda --arch x86_64
```

Checks never start jobs. They compare hard capacities first, then available
RAM and root storage from observations younger than five minutes. They leave
the larger of 256 MiB or 10% of RAM spare, and 1 GiB of root storage spare.
Swap is reported separately and never counted as RAM. CPU load is a hint
about contention; slots are not a CPU reservation. A `fits` result does not
establish application compatibility, GPU VRAM, sustained thermal performance,
or network/storage throughput.

`blocked` means a known constraint fails; `unknown` means required information
is missing; `check` means fresh readings or a separate check are needed.
For `--device` checks, exit codes are 0 for fits, 2 for blocked and 3 for
unknown/check. Invalid inputs or command failures exit 1. Comparing all devices
exits 0 after reporting each result.

SSH refresh uses existing SSH configuration and trusted host keys, disables
interactive authentication, and times out after 22 seconds. The remote host
needs `python3`; fastfetch and lscpu improve detection but are optional. A small
read-only Python probe is streamed over stdin without installing files.
On a device whose hostname matches the inventory, collection runs locally.
Failed refreshes preserve the last successful snapshot.

## CPU performance samples

```bash
devices bench nixos
devices bench mobile-dev
```

Each command explicitly runs a short synthetic PBKDF2-HMAC-SHA256 workload:
one worker, then up to 16 workers, about 1.5 seconds per round. The comparer
shows single/multiple-worker derivations per second and stores the observation
time, worker count, suite, Python and OpenSSL versions. Higher throughput
means faster performance on this workload. This measures CPU/crypto throughput,
not general device speed; power mode, current load and shared VPS contention
affect the result. Apple devices have no measured samples in this inventory.
Only compare scores from the same suite and settings. No Geekbench scores
or speed estimates are inferred from core count or clock frequency.

## Add or update devices

```bash
# Add and inspect another Linux host using an existing SSH target:
devices add work-server --name 'Work server' --ssh work-server

# Run on another Linux computer to add its local specs:
devices add travel-laptop --name 'Travel laptop' --local

# Add a device manually, then fill remaining fields using the editor:
devices add tablet --name 'Another tablet' --kind ipados
devices edit
devices path

# Keep refreshed hardware or benchmark results in the shared inventory:
devices refresh mobile-dev
devices pin mobile-dev
```

The inventory is versioned JSON at `~/.dotfiles/data/devices.json` when that
repository is available. It is shared by both Home Manager profiles through
`home-manager/common.nix`. `devices add`, the TUI add form, `devices edit`
and `devices pin` change that file; sync it through your usual Git workflow
to share changes between machines. Neither adding nor editing deploys a system.
Snapshots stay in `$XDG_STATE_HOME/devices/snapshots.json` (normally
`~/.local/state/devices/snapshots.json`). `pin` copies hardware and benchmark
facts back to the inventory without preserving volatile free RAM/disk readings.

An existing `$XDG_CONFIG_HOME/devices/inventory.json` takes precedence over
the repository. Without either file, the packaged seed is copied there.
Use `DEVICES_INVENTORY=/path/to/inventory.json` or
`devices --inventory /path/to/inventory.json …` to select a different inventory.
`devices path` always reports the file being used. Unknown numeric values are
JSON `null`; RAM/disk values are bytes. Displayed sizes use GiB (1024³ bytes).

The tool is installed declaratively on both hosts after each has run `nxb`.
The shared Codex context points agents to the inventory and refresh/check commands.
