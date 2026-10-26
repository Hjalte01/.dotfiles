"""Resource-placement regressions; probes and remote execution are always mocked."""

from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from devices import cli, core


def stamp(seconds_ago=0):
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()


def device():
    return {
        "id": "test-device", "name": "Test device", "kind": "linux",
        "hostname": "some-other-host", "ssh": "user@trusted-host",
        "specs": {"architecture": "x86_64", "cpu": "Example CPU", "cores": 2,
                  "threads": 4, "ram_bytes": 4 * core.GIB,
                  "disk_bytes": 20 * core.GIB, "cuda": False},
        "live": {"ram_available_bytes": 3 * core.GIB,
                 "disk_available_bytes": 10 * core.GIB, "load1": 0},
        "observed_at": stamp(), "live_observed_at": stamp(),
        "sources": [], "notes": [],
    }


def snapshot():
    d = device()
    return {key: deepcopy(d[key]) for key in (
        "hostname", "specs", "live", "observed_at", "live_observed_at")}


class PlacementTests(unittest.TestCase):
    def test_known_capacity_and_fresh_headroom_fit(self):
        self.assertEqual(core.assess(device(), ram_gib=1, cpus=2, disk_gib=2)["status"], "fits")

    def test_unknown_total_capacity_cannot_become_fit_from_free_memory(self):
        d = device()
        d["specs"]["ram_bytes"] = None
        self.assertEqual(core.assess(d, ram_gib=1)["status"], "unknown")

    def test_stale_or_missing_live_headroom_requires_a_check(self):
        for age in (None, stamp(core.FRESH_SECONDS + 1), "invalid"):
            with self.subTest(timestamp=age):
                d = device()
                d["live_observed_at"] = age
                self.assertEqual(core.assess(d, ram_gib=1, cpus=1, disk_gib=1)["status"], "check")
        d = device()
        d["live"] = {}
        self.assertEqual(core.assess(d, ram_gib=1, cpus=1, disk_gib=1)["status"], "check")

    def test_future_clock_skew_cannot_mark_headroom_fresh(self):
        d = device()
        d["live_observed_at"] = stamp(-3600)
        self.assertFalse(core.fresh(d))
        self.assertEqual(core.assess(d, ram_gib=1)["status"], "check")

    def test_hard_limits_block_even_with_unreliable_live_data(self):
        for requirements in ({"ram_gib": 5}, {"disk_gib": 21}, {"cpus": 5}):
            with self.subTest(requirements=requirements):
                d = device()
                d["live_observed_at"] = None
                self.assertEqual(core.assess(d, **requirements)["status"], "blocked")

    def test_ram_reserve_preserves_operating_system_headroom(self):
        d = device()
        d["live"]["ram_available_bytes"] = int(1.3 * core.GIB)
        self.assertEqual(core.assess(d, ram_gib=1)["status"], "blocked")
        d["live"]["ram_available_bytes"] = int(1.5 * core.GIB)
        self.assertEqual(core.assess(d, ram_gib=1)["status"], "fits")

    def test_disk_reserve_is_not_available_to_the_job(self):
        d = device()
        d["live"]["disk_available_bytes"] = int(1.5 * core.GIB)
        self.assertEqual(core.assess(d, disk_gib=1)["status"], "blocked")
        d["live"]["disk_available_bytes"] = 2 * core.GIB
        self.assertEqual(core.assess(d, disk_gib=1)["status"], "fits")

    def test_fractional_cpu_quota_is_a_hard_capacity(self):
        d = device()
        d["specs"].update(threads=1, cpu_quota_cores=.5)
        self.assertEqual(core.assess(d, cpus=1)["status"], "blocked")

    def test_busy_cpu_requires_review(self):
        d = device()
        d["live"]["load1"] = 4
        self.assertEqual(core.assess(d, cpus=1)["status"], "check")

    def test_cuda_states_and_architecture_requirements(self):
        for support, status in ((False, "blocked"), (None, "unknown"), (True, "check")):
            with self.subTest(cuda=support):
                d = device()
                d["specs"]["cuda"] = support
                self.assertEqual(core.assess(d, cuda=True)["status"], status)
        self.assertEqual(core.assess(device(), architecture="aarch64")["status"], "blocked")
        d = device()
        d["specs"].pop("architecture")
        self.assertEqual(core.assess(d, architecture="x86_64")["status"], "unknown")

    def test_apple_devices_are_not_linux_execution_targets(self):
        for kind in ("ios", "ipados"):
            with self.subTest(kind=kind):
                d = device()
                d["kind"] = kind
                self.assertEqual(core.assess(d, ram_gib=1)["status"], "blocked")
                with patch.object(core.subprocess, "run") as run:
                    with self.assertRaises(ValueError):
                        core.run_probe(d)
                    run.assert_not_called()

    def test_nonfinite_and_negative_requirements_are_rejected(self):
        for value in (-1, float("nan"), float("inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    core.assess(device(), ram_gib=value)


class ProbeTests(unittest.TestCase):
    def test_remote_uses_existing_trust_and_sends_probe_on_stdin(self):
        result = subprocess.CompletedProcess([], 0, json.dumps(snapshot()), "")
        with patch.object(core, "is_local", return_value=False), patch.object(core.subprocess, "run", return_value=result) as run:
            self.assertEqual(core.run_probe(device())["specs"]["threads"], 4)
        args, kwargs = run.call_args
        argv = args[0]
        self.assertEqual(argv[0], "ssh")
        self.assertIn("BatchMode=yes", argv)
        self.assertIn("StrictHostKeyChecking=yes", argv)
        self.assertIn("ConnectTimeout=6", argv)
        self.assertEqual(argv[-2], "user@trusted-host")
        self.assertEqual(argv[-1], "python3 -")
        self.assertIn("def collect", kwargs["input"])
        self.assertLessEqual(kwargs["timeout"], 30)
        self.assertFalse(kwargs.get("shell", False))

    def test_invalid_ssh_targets_never_reach_subprocess(self):
        for target in ("-oProxyCommand=bad", "host name", "host;cmd", "$(id)", "host\ncmd"):
            with self.subTest(target=target), patch.object(core, "is_local", return_value=False), patch.object(core.subprocess, "run") as run:
                d = device()
                d["ssh"] = target
                with self.assertRaises(ValueError):
                    core.run_probe(d)
                run.assert_not_called()

    def test_hostname_match_uses_local_probe_even_with_ssh_alias(self):
        from devices import probe
        d = device()
        with patch.object(core.socket, "gethostname", return_value=d["hostname"]), patch.object(probe, "collect", return_value=snapshot()) as collect, patch.object(core.subprocess, "run") as run:
            self.assertEqual(core.run_probe(d)["specs"]["threads"], 4)
            collect.assert_called_once_with()
            run.assert_not_called()

    def test_invalid_remote_snapshots_are_rejected(self):
        for value in ([], {}, {"specs": []}, {"live": "broken"}):
            with self.subTest(snapshot=value), patch.object(core, "is_local", return_value=False), patch.object(core.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, json.dumps(value), "")):
                with self.assertRaises(ValueError):
                    core.run_probe(device())

    def test_incomplete_benchmark_rates_fail_with_a_useful_error(self):
        valid = {"suite": "pbkdf2-sha256-v1", "unit": "derivations/s",
                 "observed_at": stamp(), "single": 10, "multi": 20, "workers": 2}
        for field, value in (("single", None), ("multi", float("nan")), ("workers", 1.5)):
            invalid = {**valid, field: value}
            with self.subTest(field=field), patch.object(core, "is_local", return_value=False), patch.object(core.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, json.dumps(invalid), "")):
                with self.assertRaises(ValueError):
                    core.run_probe(device(), benchmark=True)


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.inventory = Path(self.tmp.name) / "inventory.json"
        self.environment = patch.dict(os.environ, {
            "DEVICES_INVENTORY": str(self.inventory),
            "XDG_STATE_HOME": str(Path(self.tmp.name) / "state"),
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.baseline = device()
        self.baseline.pop("live")
        self.baseline.pop("live_observed_at")
        core.atomic_json(self.inventory, {"version": 1, "devices": [self.baseline]})

    def test_failed_refresh_preserves_last_good_snapshot(self):
        core.cache_update("test-device", snapshot())
        before = core.state_path().read_bytes()
        for failure in (ValueError("SSH failed"), subprocess.TimeoutExpired(["ssh"], 22)):
            with self.subTest(failure=type(failure).__name__), patch.object(core, "run_probe", side_effect=failure):
                with self.assertRaises(type(failure)):
                    core.refresh_device(device())
                self.assertEqual(core.state_path().read_bytes(), before)

    def test_malformed_remote_refresh_also_preserves_cache(self):
        core.cache_update("test-device", snapshot())
        before = core.state_path().read_bytes()
        malformed = subprocess.CompletedProcess([], 0, '{"specs": [], "live": "broken"}', "")
        with patch.object(core, "is_local", return_value=False), patch.object(core.subprocess, "run", return_value=malformed):
            with self.assertRaises(ValueError):
                core.refresh_device(device())
        self.assertEqual(core.state_path().read_bytes(), before)

    def test_pin_keeps_measured_hardware_after_cache_is_removed(self):
        measured = snapshot()
        measured["specs"].update(cpu="Newly measured CPU", threads=8)
        measured["source"] = "Measured in test"
        measured["benchmark"] = {"suite": "example", "single": 10, "multi": 20, "workers": 2}
        core.cache_update("test-device", measured)
        with patch.object(sys, "argv", ["devices", "pin", "test-device"]), redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(), 0)
        core.state_path().unlink()
        pinned = core.find_device("test-device")
        self.assertEqual(pinned["specs"]["cpu"], "Newly measured CPU")
        self.assertEqual(pinned["specs"]["threads"], 8)
        self.assertEqual(pinned["benchmark"]["multi"], 20)
        self.assertEqual(pinned["source"], "Measured in test")
        self.assertNotIn("live", pinned)
        self.assertNotIn("live_observed_at", pinned)

    def test_json_default_and_list_subcommand_produce_parseable_inventory(self):
        for argv in (["devices", "--json"], ["devices", "list", "--json"]):
            with self.subTest(argv=argv), patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()) as output:
                self.assertEqual(cli.main(), 0)
                value = json.loads(output.getvalue())
                self.assertEqual(value["devices"][0]["id"], "test-device")
                self.assertEqual(value["inventory_path"], str(self.inventory))


if __name__ == "__main__":
    unittest.main()
