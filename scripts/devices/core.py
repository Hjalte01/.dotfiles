"""Offline-first inventory and conservative job placement guidance."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile

GIB = 1024 ** 3
FRESH_SECONDS = 300


def seed_path():
    return Path(os.environ.get("DEVICES_SEED", Path(__file__).resolve().parents[2] / "data/devices.json"))


def inventory_path():
    if custom := os.environ.get("DEVICES_INVENTORY"):
        return Path(custom).expanduser()
    config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "devices/inventory.json"
    repo = Path.home() / ".dotfiles/data/devices.json"
    if config.exists():
        return config
    if repo.exists():
        return repo
    if not config.exists():
        atomic_json(config, read_json(seed_path()))
    return config


def state_path():
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "devices/snapshots.json"


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot read {path}: {exc}") from exc


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, prefix=".devices-", delete=False) as stream:
            temp = Path(stream.name)
            json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
        temp.replace(path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


@contextmanager
def locked(path):
    lock = state_path().parent / "locks" / (hashlib.sha256(str(path.resolve()).encode()).hexdigest() + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def validate_device(device):
    if not isinstance(device, dict) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", str(device.get("id", ""))):
        raise ValueError("Device IDs must contain lowercase letters, digits, underscores or hyphens.")
    for field in ("name", "kind"):
        if not isinstance(device.get(field), str) or not device[field].strip():
            raise ValueError(f"Device {device['id']} needs a {field}.")
    if device["kind"] not in ("linux", "ios", "ipados", "other"):
        raise ValueError("Device kind must be linux, ios, ipados or other.")
    if target := device.get("ssh"):
        validate_target(target)
    specs = device.get("specs", {})
    if not isinstance(specs, dict):
        raise ValueError("specs must be an object.")
    for key in ("cores", "threads", "ram_bytes", "disk_bytes", "swap_bytes"):
        value = specs.get(key)
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
            raise ValueError(f"{key} must be a nonnegative number or null.")
    for key in ("cores", "threads"):
        if specs.get(key) is not None and int(specs[key]) != specs[key]:
            raise ValueError(f"{key} must be a whole number.")
    if specs.get("cuda") is not None and type(specs["cuda"]) is not bool:
        raise ValueError("cuda must be true, false or null.")
    for key in ("notes", "sources"):
        if key in device and not isinstance(device[key], list):
            raise ValueError(f"{key} must be an array.")


def validate_target(target):
    if not isinstance(target, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.@:-]*", target):
        raise ValueError("SSH target must be a hostname or user@hostname, without options or whitespace.")


def read_inventory():
    data = read_json(inventory_path())
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("devices"), list):
        raise ValueError("Expected an inventory with version: 1 and a devices array.")
    seen = set()
    for device in data["devices"]:
        validate_device(device)
        if device["id"] in seen:
            raise ValueError(f"Duplicate device ID: {device['id']}")
        seen.add(device["id"])
    return data


def load_devices():
    devices = read_inventory()["devices"]
    cache = read_json(state_path()) if state_path().exists() else {}
    if not isinstance(cache, dict) or any(not isinstance(value, dict) for value in cache.values()):
        raise ValueError(f"Invalid snapshot cache: {state_path()}")
    for device in devices:
        if snapshot := cache.get(device["id"]):
            for key in ("specs", "live"):
                if key in snapshot:
                    device[key] = {**device.get(key, {}), **snapshot[key]}
            for key in ("hostname", "observed_at", "live_observed_at", "source", "benchmark"):
                if key in snapshot:
                    device[key] = snapshot[key]
    return devices


def save_device(device):
    validate_device(device)
    path = inventory_path()
    with locked(path):
        data = read_inventory()
        existing = next((i for i, d in enumerate(data["devices"]) if d["id"] == device["id"]), None)
        if existing is None:
            data["devices"].append(device)
        else:
            data["devices"][existing] = device
        atomic_json(path, data)


def cache_update(device_id, update):
    path = state_path()
    with locked(path):
        cache = read_json(path) if path.exists() else {}
        cache[device_id] = {**cache.get(device_id, {}), **update}
        atomic_json(path, cache)


def find_device(identifier):
    for device in load_devices():
        if device["id"] == identifier:
            return device
    raise ValueError(f"Unknown device: {identifier}. Run devices list for IDs.")


def is_local(device):
    return device.get("hostname") == socket.gethostname()


def run_probe(device, benchmark=False):
    if device["kind"] != "linux":
        raise ValueError("Automatic probes require Linux. Edit Apple device specs in the inventory.")
    if is_local(device):
        from . import probe
        value = probe.benchmark() if benchmark else probe.collect()
        validate_probe(value, benchmark=benchmark)
        return value
    if not (target := device.get("ssh")):
        raise ValueError("Set this device's ssh target or matching local hostname first.")
    validate_target(target)
    script = Path(__file__).with_name("probe.py").read_text()
    remote = "python3 - --benchmark" if benchmark else "python3 -"
    result = subprocess.run(
        ["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
         "-o", "ConnectTimeout=6", "-o", "ConnectionAttempts=1", target, remote],
        input=script, capture_output=True, text=True, timeout=22,
    )
    if result.returncode:
        raise ValueError(f"Probe failed for {device['id']}: {result.stderr.strip()[-600:]}")
    try:
        value = json.loads(result.stdout)
    except ValueError as exc:
        raise ValueError("Remote probe did not return JSON; check the remote noninteractive shell.") from exc
    validate_probe(value, benchmark=benchmark)
    return value


def validate_probe(value, benchmark=False):
    """Reject incomplete replies before they can replace a usable cached reading."""
    if not isinstance(value, dict):
        raise ValueError("Probe returned an invalid snapshot.")
    if benchmark:
        if not all(isinstance(value.get(key), str) and value[key] for key in ("suite", "unit", "observed_at")):
            raise ValueError("Probe returned an incomplete benchmark.")
        fields = {key: value.get(key) for key in ("single", "multi", "workers")}
    else:
        if not all(isinstance(value.get(key), dict) for key in ("specs", "live")):
            raise ValueError("Probe returned invalid specs or live readings.")
        if not all(isinstance(value.get(key), str) and value[key] for key in ("hostname", "observed_at", "live_observed_at")):
            raise ValueError("Probe returned an incomplete timestamped snapshot.")
        if not all(key in value["specs"] for key in ("threads", "ram_bytes", "disk_bytes")):
            raise ValueError("Probe omitted resource capacities.")
        if not all(key in value["live"] for key in ("ram_available_bytes", "disk_available_bytes", "load1")):
            raise ValueError("Probe omitted live resource readings.")
        validate_device({"id": "probe", "name": "Probe", "kind": "linux", "specs": value["specs"]})
        fields = value["live"]
    for key, amount in fields.items():
        if amount is not None and (type(amount) not in (int, float) or not math.isfinite(amount) or amount < 0):
            raise ValueError(f"Probe returned an invalid {key} value.")
    if benchmark and (not all(type(value.get(key)) in (int, float) and value[key] > 0 for key in ("single", "multi", "workers")) or type(value.get("workers")) is not int):
        raise ValueError("Probe returned invalid benchmark rates or worker count.")


def refresh_device(device):
    snapshot = run_probe(device)
    cache_update(device["id"], snapshot)
    return find_device(device["id"])


def benchmark_device(device):
    result = run_probe(device, benchmark=True)
    cache_update(device["id"], {"benchmark": result})
    return result


def age_seconds(timestamp):
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(timestamp.replace("Z", "+00:00"))).total_seconds()
        return max(0, age) if age >= -30 else None
    except (ValueError, TypeError, AttributeError):
        return None


def fresh(device):
    age = age_seconds(device.get("live_observed_at"))
    return age is not None and age <= FRESH_SECONDS


def gib(value):
    return "?" if value is None else f"{value / GIB:.2f}"


def assess(device, ram_gib=0, cpus=0, disk_gib=0, cuda=False, architecture=None):
    """Check hard capacities, then current headroom; never submit or reserve work."""
    for value in (ram_gib, cpus, disk_gib):
        if not math.isfinite(value) or value < 0:
            raise ValueError("Job requirements must be finite nonnegative numbers.")
    specs, live = device.get("specs", {}), device.get("live", {})
    blocked, unknown, checks, info = [], [], [], []
    if device["kind"] != "linux":
        return {"status": "blocked", "reasons": ["This device is recorded as a client, without a Linux execution target."],
                "live_observed_at": device.get("live_observed_at"), "fresh": fresh(device)}
    if architecture:
        actual = specs.get("architecture")
        if not actual:
            unknown.append("CPU architecture is unknown.")
        elif architecture != actual:
            blocked.append(f"Requires {architecture}; device is {actual}.")
    if cuda:
        support = specs.get("cuda")
        if support is False:
            blocked.append("No usable CUDA GPU recorded.")
        elif support is not True:
            unknown.append("CUDA support has not been verified.")
        else:
            checks.append("Check free GPU VRAM and the required CUDA/framework versions separately.")
    for key, request, label in (("threads", cpus, "CPU slots"), ("ram_bytes", ram_gib * GIB, "RAM"), ("disk_bytes", disk_gib * GIB, "root disk")):
        if not request:
            continue
        capacity = specs.get(key)
        if key == "threads" and specs.get("cpu_quota_cores") is not None:
            capacity = min(capacity, specs["cpu_quota_cores"]) if capacity is not None else specs["cpu_quota_cores"]
        if capacity is None:
            unknown.append(f"{label} capacity is unknown.")
        elif capacity < request:
            blocked.append(f"Insufficient total {label}: {capacity if key == 'threads' else gib(capacity)} {'slots' if key == 'threads' else 'GiB'}.")
    for key, request, reserve, label in (
        ("ram_available_bytes", ram_gib * GIB, max(.25 * GIB, .1 * (specs.get("ram_bytes") or 0)), "RAM"),
        ("disk_available_bytes", disk_gib * GIB, GIB, "root disk"),
    ):
        if not request:
            continue
        if not fresh(device) or live.get(key) is None:
            checks.append(f"Refresh {label} headroom (cached readings expire after 5 minutes).")
        elif live[key] < request + reserve:
            blocked.append(f"Insufficient available {label}: {gib(live[key])} GiB, keeping {gib(reserve)} GiB spare.")
        else:
            info.append(f"{label}: {gib(live[key])} GiB available, {gib(reserve)} GiB kept spare.")
    if cpus:
        if not fresh(device) or live.get("load1") is None:
            checks.append("Refresh CPU load before starting; CPU slots are capacity, not a reservation.")
        elif specs.get("threads") and live["load1"] + cpus > specs["threads"]:
            checks.append(f"CPU may be busy (1-minute load {live['load1']:.2f}); slots are not reserved.")
        else:
            info.append("CPU slots fit; current load is only an estimate of contention.")
    if not any((ram_gib, cpus, disk_gib, cuda, architecture)):
        checks.append("Supply at least one job requirement to assess capacity.")
    status = "blocked" if blocked else "unknown" if unknown else "check" if checks else "fits"
    return {"status": status, "reasons": blocked + unknown + checks + info or ["No resource requirements supplied."],
            "live_observed_at": device.get("live_observed_at"), "fresh": fresh(device)}


def detail_lines(device):
    s, live = device.get("specs", {}), device.get("live", {})
    lines = [f"{device['name']}  [{device['id']}]", f"{s.get('os') or '?'} · {s.get('architecture') or '?'} · {device['kind']}",
             f"CPU: {s.get('cpu') or '?'}", f"CPU slots: {s.get('threads') or '?'}" + (" vCPUs (shared host)" if s.get('virtualized') else f" threads / {s.get('cores') or '?'} cores"),
             f"RAM: {gib(s.get('ram_bytes'))} GiB usable; available {gib(live.get('ram_available_bytes'))} GiB",
             f"Root disk: {gib(s.get('disk_bytes'))} GiB; available {gib(live.get('disk_available_bytes'))} GiB",
             f"Swap: {gib(s.get('swap_bytes'))} GiB", f"GPU: {s.get('gpu') or '?'} · CUDA: {s.get('cuda') if s.get('cuda') is not None else '?'}",
             f"Hardware observed: {device.get('observed_at') or 'unverified'} · {device.get('source') or '?'}",
             f"Live readings: {device.get('live_observed_at') or 'none'} ({'fresh, <5 min' if fresh(device) else 'cached / unavailable'})",
             f"Confidence: {device.get('confidence') or 'see sources'}"]
    if device.get("ssh"):
        lines.append(f"SSH target: {device['ssh']}")
    if b := device.get("benchmark"):
        lines += [f"CPU sample: {b['single']:.1f} single / {b['multi']:.1f} multi {b.get('unit', 'ops/s')} ({b['workers']} workers)",
                  f"Benchmark: {b['suite']} · {b.get('observed_at', '?')}", "Synthetic CPU sample only; does not measure application, disk or GPU performance."]
    else:
        lines.append("CPU sample: not measured · devices bench ID (optional, uses CPU briefly)")
    lines.extend(f"• {note}" for note in device.get("notes", []))
    lines.extend(f"Source: {source['label']} — {source['url']}" for source in device.get("sources", []))
    return lines
