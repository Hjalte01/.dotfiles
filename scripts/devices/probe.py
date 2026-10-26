#!/usr/bin/env python3
"""Small, standalone Linux probe; safe to send to ``ssh HOST python3 -``.

Only --benchmark runs a CPU workload. Ordinary collection reads system metadata.
The JSON deliberately omits usernames, addresses, serial numbers and UUIDs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import ssl
import subprocess
import sys
import time


def timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def read(path: str | Path) -> str:
    try:
        return Path(path).read_text().strip()
    except (OSError, UnicodeError):
        return ""


def command(args: list[str], timeout: float = 3) -> str:
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "LC_ALL": "C"}, check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, UnicodeError, subprocess.TimeoutExpired):
        return ""


def json_command(args: list[str], timeout: float = 3):
    try:
        return json.loads(command(args, timeout))
    except (ValueError, TypeError):
        return None


def positive_int(value):
    try:
        parsed = int(value)
        return parsed if parsed > 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def cgroup_dirs() -> list[Path]:
    """Current v2 cgroup and ancestors, including inherited resource limits."""
    base = Path("/sys/fs/cgroup")
    entry = next((line[3:] for line in read("/proc/self/cgroup").splitlines()
                  if line.startswith("0::")), "")
    parts = Path(entry.lstrip("/")).parts
    if ".." in parts:
        return [base]
    current = base.joinpath(*parts)
    result = []
    while current == base or base in current.parents:
        result.append(current)
        if current == base:
            break
        current = current.parent
    return result


def allocations() -> tuple[int, float | None, list[tuple[int, int | None]]]:
    threads = os.cpu_count() or 1
    try:
        threads = min(threads, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        pass
    quotas = []
    memory_limits = []
    for directory in cgroup_dirs():
        fields = read(directory / "cpu.max").split()
        if len(fields) == 2:
            quota, period = map(positive_int, fields)
            if quota and period:
                quotas.append(quota / period)
        limit = positive_int(read(directory / "memory.max"))
        if limit:
            current = read(directory / "memory.current")
            try:
                used = max(0, int(current))
            except ValueError:
                used = None
            memory_limits.append((limit, used))
    quota = min(quotas) if quotas else None
    # Fractional quotas do not constitute another fully available CPU worker.
    if quota is not None:
        threads = min(threads, max(1, math.floor(quota)))
    return max(1, threads), quota, memory_limits


def collect() -> dict:
    if platform.system() != "Linux":
        raise ValueError("Automatic probing currently supports Linux only.")
    observed = timestamp()
    ff_raw = json_command([
        "fastfetch", "--format", "json", "--structure",
        "OS:Host:CPU:GPU:Memory:Swap:Disk",
    ], timeout=8)
    ff = {item.get("type"): item["result"] for item in ff_raw
          if isinstance(item, dict) and "result" in item} if isinstance(ff_raw, list) else {}
    lscpu_raw = json_command(["lscpu", "-J"])
    lscpu = {item.get("field", "").rstrip(":"): item.get("data")
             for item in lscpu_raw.get("lscpu", [])
             if isinstance(item, dict)} if isinstance(lscpu_raw, dict) else {}
    cpuinfo = read("/proc/cpuinfo")
    cpu_fields = {}
    for line in cpuinfo.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            cpu_fields.setdefault(key.strip(), value.strip())
    cpu = ff.get("CPU", {})
    if not isinstance(cpu, dict):
        cpu = {}
    host = ff.get("Host", {})
    if not isinstance(host, dict):
        host = {}
    product = host.get("version")
    if not product or str(product).isdigit():
        product = host.get("name") or read("/sys/class/dmi/id/product_name")
    host_description = " ".join(str(x) for x in [
        product, host.get("family", ""), host.get("vendor", ""),
        read("/sys/class/dmi/id/sys_vendor"),
    ]).lower()
    virtualized = bool(lscpu.get("Hypervisor vendor")) or "hypervisor" in cpu_fields.get("flags", "").split()
    virtualized = virtualized or any(name in host_description for name in (
        "kvm", "qemu", "vmware", "virtualbox", "virtual machine", "vserver",
        "amazon ec2", "google compute", "xen", "openstack", "bhyve",
    ))
    physical = cpu.get("cores", {})
    cores = positive_int(physical.get("physical")) if isinstance(physical, dict) else None
    if cores is None:
        sockets = positive_int(lscpu.get("Socket(s)"))
        per_socket = positive_int(lscpu.get("Core(s) per socket"))
        if sockets and per_socket:
            cores = sockets * per_socket
    threads, quota, memory_limits = allocations()
    if virtualized:
        cores = None  # Guest topology does not reveal physical host allocation.
    elif cores is not None:
        cores = min(cores, threads)
    meminfo = {}
    for line in read("/proc/meminfo").splitlines():
        match = re.fullmatch(r"(\w+):\s+(\d+)\s+kB", line)
        if match:
            meminfo[match[1]] = int(match[2]) * 1024
    ram_total = meminfo.get("MemTotal")
    ram_available = meminfo.get("MemAvailable", meminfo.get("MemFree"))
    for limit, used in memory_limits:
        ram_total = min(ram_total, limit) if ram_total is not None else limit
        if used is not None:
            remaining = max(0, limit - used)
            ram_available = min(ram_available, remaining) if ram_available is not None else remaining
    if ram_total is not None and ram_available is not None:
        ram_available = min(ram_total, ram_available)
    try:
        disk = os.statvfs("/")
        disk_total = disk.f_blocks * disk.f_frsize
        disk_available = disk.f_bavail * disk.f_frsize
    except OSError:
        disk_total = disk_available = None
    gpu_result = ff.get("GPU", [])
    if not isinstance(gpu_result, list):
        gpu_result = []
    gpu_names = [str(item["name"]) for item in gpu_result
                 if isinstance(item, dict) and item.get("name")]
    vendors = []
    try:
        cards = list(Path("/sys/class/drm").glob("card[0-9]*"))
    except OSError:
        cards = []
    for card in cards:
        if re.fullmatch(r"card\d+", card.name):
            vendor = read(card / "device/vendor").lower()
            if vendor:
                vendors.append(vendor)
    if not gpu_names:
        labels = {"0x1002": "AMD GPU", "0x8086": "Intel GPU",
                  "0x10de": "NVIDIA GPU", "0x1af4": "Virtio display GPU",
                  "0x1b36": "QEMU display GPU", "0x1234": "QEMU display GPU"}
        gpu_names = list(dict.fromkeys(labels[v] for v in vendors if v in labels))
    cuda = None
    nvidia_device = any(Path("/dev").glob("nvidia[0-9]*"))
    if nvidia_device or "0x10de" in vendors or any("nvidia" in name.lower() for name in gpu_names):
        # An NVIDIA display device alone does not prove a working CUDA runtime.
        names = command(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], timeout=3)
        if names:
            cuda = True
    elif gpu_names and all(not any(token in name.lower() for token in ("unknown", "nvidia"))
                           for name in gpu_names):
        cuda = False
    os_fields = {}
    for line in read("/etc/os-release").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            os_fields[key] = value.strip('"\'')
    os_result = ff.get("OS", {})
    if not isinstance(os_result, dict):
        os_result = {}
    try:
        load = os.getloadavg()[0]
    except OSError:
        load = None
    specs = {
        "os": os_result.get("prettyName") or os_fields.get("PRETTY_NAME") or "Linux",
        "architecture": platform.machine(),
        "cpu": cpu.get("cpu") or lscpu.get("Model name") or cpu_fields.get("model name") or cpu_fields.get("Hardware") or "Unknown",
        "cores": cores,
        "threads": threads,
        "ram_bytes": ram_total,
        "disk_bytes": disk_total,
        "swap_bytes": meminfo.get("SwapTotal"),
        "gpu": ", ".join(gpu_names) or "Unknown / not detected",
        "cuda": cuda,
        "virtualized": virtualized,
        "model": product or None,
    }
    if quota is not None:
        specs["cpu_quota_cores"] = quota
    sources = ["Linux /proc", "root statvfs", "CPU affinity / cgroup v2 limits"]
    if ff:
        sources.append("fastfetch JSON")
    if lscpu:
        sources.append("lscpu JSON")
    return {
        "hostname": platform.node(),
        "specs": specs,
        "live": {"ram_available_bytes": ram_available,
                 "disk_available_bytes": disk_available, "load1": load},
        "observed_at": observed,
        "live_observed_at": timestamp(),
        "source": "; ".join(sources),
    }


_WORKER = r'''
import hashlib, json, sys, time
duration = float(sys.argv[1])
count = 0
start = time.perf_counter()
while time.perf_counter() - start < duration:
    hashlib.pbkdf2_hmac("sha256", b"device-performance-v1", b"device-comparer-salt", 20000, dklen=32)
    count += 1
print(json.dumps({"count": count}))
'''


def benchmark_round(workers: int, seconds: float) -> float:
    children = []
    start = time.perf_counter()
    try:
        for _ in range(workers):
            children.append(subprocess.Popen(
                [sys.executable, "-c", _WORKER, str(seconds)],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True,
            ))
        count = 0
        deadline = start + seconds + 15
        for child in children:
            output, errors = child.communicate(timeout=max(0.1, deadline - time.perf_counter()))
            if child.returncode:
                raise RuntimeError("Benchmark worker failed: " + errors.strip()[:300])
            count += int(json.loads(output)["count"])
        elapsed = time.perf_counter() - start
        return round(count / elapsed, 3)
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait()


def benchmark(seconds: float = 1.5) -> dict:
    if not math.isfinite(seconds) or not 0.05 <= seconds <= 15:
        raise ValueError("Benchmark seconds must be between 0.05 and 15.")
    if not hasattr(hashlib, "pbkdf2_hmac"):
        raise RuntimeError("This Python installation has no PBKDF2 support.")
    threads, _, _ = allocations()
    workers = min(16, threads)
    return {
        "suite": "pbkdf2-sha256-v1",
        "unit": "derivations/s",
        "single": benchmark_round(1, seconds),
        "multi": benchmark_round(workers, seconds),
        "workers": workers,
        "seconds_per_round": seconds,
        "observed_at": timestamp(),
        "python": platform.python_version(),
        "openssl": ssl.OPENSSL_VERSION,
        "notes": "Fixed PBKDF2-HMAC-SHA256, 20000 iterations, dklen=32; rates include process startup. Synthetic CPU/crypto throughput, not universal application performance. Multi workers capped at 16 and available CPU allocation; affected by load, power policy, Python/OpenSSL and provider contention.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", action="store_true", help="Run an explicit short CPU benchmark")
    parser.add_argument("--seconds", type=float, default=1.5, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        result = benchmark(args.seconds) if args.benchmark else collect()
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print("devices probe: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
