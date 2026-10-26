"""Compare devices, refresh Linux snapshots, and check job requirements."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys

from . import core


def number(value):
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise argparse.ArgumentTypeError("Use a finite nonnegative number.")
    return result


def print_json(value):
    print(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False))


def list_devices(devices):
    headings = ("ID", "CPU slots", "RAM GiB", "Free RAM*", "Root free*", "CPU")
    rows = []
    for d in devices:
        s, live = d.get("specs", {}), d.get("live", {})
        slots = str(s.get("threads") or "?") + (" vCPU" if s.get("virtualized") else "")
        rows.append((d["id"], slots, core.gib(s.get("ram_bytes")), core.gib(live.get("ram_available_bytes")),
                     core.gib(live.get("disk_available_bytes")), s.get("cpu") or "unconfirmed"))
    widths = [max(len(str(row[i])) for row in [headings, *rows]) for i in range(len(headings))]
    for row in [headings, *rows]:
        print("  ".join(str(cell).ljust(width) for cell, width in zip(row, widths)))
    print("\n* GiB from saved snapshots; check timestamps with devices show ID, refresh before placing jobs.")
    print("CPU slots describe capacity. Use devices bench ID for an optional CPU performance sample.")


def add(args):
    identifier = args.id or input("Device ID (e.g. work-laptop): ").strip()
    if any(d["id"] == identifier for d in core.load_devices()):
        raise ValueError(f"Device {identifier} already exists. Use devices edit to change it.")
    name = args.name or (identifier if args.id else input("Display name: ").strip())
    device = {"id": identifier, "name": name, "kind": args.kind, "specs": {}, "notes": [], "sources": []}
    if args.local:
        device["hostname"] = socket.gethostname()
    if args.ssh:
        device["ssh"] = args.ssh
    if args.cpu:
        device["specs"]["cpu"] = args.cpu
    if args.ram is not None:
        device["specs"]["ram_bytes"] = round(args.ram * core.GIB)
    if args.cpus is not None:
        device["specs"]["threads"] = args.cpus
    # Persist measured hardware with new devices so it travels with the inventory.
    if args.local or args.ssh:
        snapshot = core.run_probe(device)
        device.update({k: v for k, v in snapshot.items() if k not in ("live", "live_observed_at")})
        core.save_device(device)
        core.cache_update(identifier, snapshot)
    else:
        core.save_device(device)
    print(f"Added {identifier} to {core.inventory_path()}")


def main():
    parser = argparse.ArgumentParser(prog="devices", description=__doc__)
    parser.add_argument("--json", action="store_true", help="Machine-readable merged inventory")
    parser.add_argument("--inventory", type=Path, help="Use a different inventory JSON file")
    sub = parser.add_subparsers(dest="action")
    sub.add_parser("tui", help="Open the terminal comparer")
    sub.add_parser("list", help="Print all devices").add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    show = sub.add_parser("show", help="Print full specs, timestamps and sources")
    show.add_argument("id")
    show.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    refresh = sub.add_parser("refresh", help="Read fresh specs and availability from Linux hosts")
    refresh.add_argument("id", help="Device ID, or all (Linux only)")
    bench = sub.add_parser("bench", help="Opt-in synthetic CPU sample (~4 seconds of CPU per host)")
    bench.add_argument("id", help="Linux device ID")
    bench.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    check = sub.add_parser("check", help="Check Linux job capacity; never starts a job")
    check.add_argument("--device", help="Only assess this device ID")
    check.add_argument("--ram", type=number, default=0, help="Required usable RAM in GiB")
    check.add_argument("--cpus", type=int, default=0, help="Required logical CPU slots")
    check.add_argument("--disk", type=number, default=0, help="Required free root storage in GiB")
    check.add_argument("--cuda", action="store_true", help="Require NVIDIA CUDA")
    check.add_argument("--arch", help="Required architecture, e.g. x86_64 or aarch64")
    check.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    add_parser = sub.add_parser("add", help="Add a device; probe Linux with --local or --ssh")
    add_parser.add_argument("id", nargs="?")
    add_parser.add_argument("--name")
    add_parser.add_argument("--kind", choices=["linux", "ios", "ipados", "other"], default="linux")
    connection = add_parser.add_mutually_exclusive_group()
    connection.add_argument("--local", action="store_true")
    connection.add_argument("--ssh", help="An existing trusted SSH target; requires remote python3")
    add_parser.add_argument("--cpu")
    add_parser.add_argument("--cpus", type=int)
    add_parser.add_argument("--ram", type=number, help="Usable RAM in GiB")
    sub.add_parser("edit", help="Edit inventory JSON using $EDITOR")
    sub.add_parser("path", help="Print the active inventory path")
    pin = sub.add_parser("pin", help="Save cached hardware/benchmark into the shared inventory")
    pin.add_argument("id")
    args = parser.parse_args()
    if args.inventory:
        os.environ["DEVICES_INVENTORY"] = str(args.inventory)
    action = args.action or ("list" if args.json or not sys.stdin.isatty() or not sys.stdout.isatty() else "tui")
    try:
        if action == "path":
            print(core.inventory_path())
        elif action == "tui":
            from .app import DevicesApp
            DevicesApp().run()
        elif action == "list":
            devices = core.load_devices()
            if args.json:
                print_json({"version": 1, "inventory_path": str(core.inventory_path()), "devices": devices})
            else:
                list_devices(devices)
        elif action == "show":
            device = core.find_device(args.id)
            print_json(device) if args.json else print("\n".join(core.detail_lines(device)))
        elif action == "refresh":
            devices = [d for d in core.load_devices() if d["kind"] == "linux"] if args.id == "all" else [core.find_device(args.id)]
            failed = False
            for device in devices:
                print(f"Reading {device['id']}…", flush=True)
                try:
                    updated = core.refresh_device(device)
                    print(f"  Updated {updated['live_observed_at']}")
                except (ValueError, OSError, subprocess.SubprocessError) as exc:
                    print(f"  {exc}", file=sys.stderr)
                    failed = True
            return int(failed)
        elif action == "bench":
            device = core.find_device(args.id)
            if not args.json:
                print(f"Sampling CPU on {device['id']} for a few seconds…", flush=True)
            sample = core.benchmark_device(device)
            if args.json:
                print_json(sample)
            else:
                print(f"Single: {sample['single']:.1f}; multi: {sample['multi']:.1f} {sample['unit']} ({sample['workers']} workers)")
                print("Synthetic PBKDF2 CPU sample. It does not measure general application, disk or GPU performance.")
        elif action == "check":
            if not any((args.ram, args.cpus, args.disk, args.cuda, args.arch)):
                raise ValueError("Supply --ram, --cpus, --disk, --cuda or --arch.")
            devices = [core.find_device(args.device)] if args.device else core.load_devices()
            results = [{"id": d["id"], **core.assess(d, args.ram, args.cpus, args.disk, args.cuda, args.arch)} for d in devices]
            if args.json:
                print_json(results)
            else:
                for result in results:
                    print(f"{result['id']}: {result['status'].upper()}")
                    for reason in result["reasons"]:
                        print(f"  {reason}")
                print("A fit is a snapshot, not a reservation. Verify job-specific software and sustained performance.")
            if args.device:
                return {"fits": 0, "blocked": 2, "unknown": 3, "check": 3}[results[0]["status"]]
        elif action == "add":
            add(args)
        elif action == "pin":
            device = core.find_device(args.id)
            device.pop("live", None)
            device.pop("live_observed_at", None)
            core.save_device(device)
            print(f"Pinned {args.id} hardware to {core.inventory_path()}")
        elif action == "edit":
            editor = shlex.split(os.environ.get("EDITOR", "nvim"))
            subprocess.run([*editor, str(core.inventory_path())], check=True)
            core.read_inventory()
        return 0
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"devices: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
