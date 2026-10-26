"""Headless interaction tests; never contacts a device or starts a workload."""
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from devices import core
from devices.app import DevicesApp, DeviceForm, JobFit, sample_label, snapshot_label
from textual.widgets import DataTable, Input, Static


GIB = 2**30


def fixture():
    return [
        {"id": "pc", "name": "My laptop", "kind": "linux", "hostname": "test-pc",
         "specs": {"cpu": "AMD Ryzen", "cores": 8, "threads": 16, "ram_bytes": 16 * GIB,
                   "disk_bytes": 100 * GIB, "gpu": "Radeon", "architecture": "x86_64", "cuda": False},
         "live": {"ram_available_bytes": 8 * GIB, "disk_available_bytes": 30 * GIB},
         "live_observed_at": datetime.now(timezone.utc).isoformat(),
         "benchmark": {"suite": "pbkdf2-sha256-v1", "unit": "derivations/s", "single": 100.04,
                       "multi": 800.04, "workers": 16, "observed_at": "2026-10-20T12:00:00Z"},
         "confidence": "measured", "notes": [], "sources": []},
        {"id": "ipad", "name": "iPad Air", "kind": "ipados", "specs": {},
         "confidence": "unconfirmed", "notes": ["Model still unknown"], "sources": []},
    ]


class Labels(unittest.TestCase):
    def test_samples_do_not_mix_benchmark_suites(self):
        self.assertEqual(sample_label({}), "not measured")
        self.assertEqual(sample_label({"benchmark": {"suite": "different-test"}}), "other suite · details")

    def test_snapshot_age_and_unknown_device_are_explicit(self):
        self.assertEqual(snapshot_label({"confidence": "unconfirmed"}), "unconfirmed")
        self.assertEqual(snapshot_label({}), "reference")
        old = datetime.now(timezone.utc) - timedelta(days=2, minutes=1)
        self.assertEqual(snapshot_label({"live_observed_at": old.isoformat()}), "cached 2d")


class DeviceUI(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        inventory = self.root / "inventory.json"
        inventory.write_text(json.dumps({"version": 1, "devices": fixture()}))
        self.stack.enter_context(patch.dict(os.environ, {
            "DEVICES_INVENTORY": str(inventory), "XDG_STATE_HOME": str(self.root / "state"),
        }))

    def tearDown(self):
        self.stack.close()

    async def test_offline_startup_navigation_age_and_small_terminal(self):
        app = DevicesApp()
        with patch.object(core, "refresh_device", side_effect=AssertionError("Unexpected probe")) as refresh:
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                self.assertEqual(app.query_one("#comparison", DataTable).row_count, 2)
                self.assertEqual(app.query_one("#comparison", DataTable).get_cell("pc", "CPU sample 1 / N"), "100.0 / 800.0")
                self.assertEqual(app.query_one("#comparison", DataTable).get_cell("ipad", "CPU sample 1 / N"), "not measured")
                self.assertIn("2026-10-20T12:00:00Z", str(app.query_one("#detail-body", Static).render()))
                self.assertEqual(app.selected()["id"], "pc")
                await pilot.press("j")
                self.assertEqual(app.selected()["id"], "ipad")
                self.assertIn("Model still unknown", str(app.query_one("#detail-body", Static).render()))
                app.update_age_labels()
                await pilot.press("ctrl+r")
                self.assertEqual(app.selected()["id"], "ipad")
                refresh.assert_not_called()

    async def test_add_preserves_unknown_specs_and_rejects_duplicate(self):
        app = DevicesApp()
        async with app.run_test(size=(100, 60)) as pilot:
            await pilot.press("a")
            self.assertIsInstance(app.screen, DeviceForm)
            app.screen.query_one("#device-id", Input).value = "pc"
            app.screen.query_one("#device-name", Input).value = "Duplicate"
            app.screen.query_one("#save-device").press()
            await pilot.pause()
            self.assertIn("already exists", str(app.screen.query_one("#form-error", Static).render()))
            app.screen.query_one("#device-id", Input).value = "new-host"
            app.screen.query_one("#device-name", Input).value = "New server"
            app.screen.query_one("#device-ssh", Input).value = "new-host"
            app.screen.query_one("#save-device").press()
            await pilot.pause()
            self.assertEqual(app.selected()["id"], "new-host")
            saved = next(device for device in core.load_devices() if device["id"] == "new-host")
            self.assertIsNone(saved["specs"]["ram_bytes"])
            self.assertIsNone(saved["specs"]["threads"])

    async def test_job_fit_checks_all_devices_and_validates_inputs(self):
        app = DevicesApp()
        async with app.run_test(size=(100, 60)) as pilot:
            await pilot.press("f")
            self.assertIsInstance(app.screen, JobFit)
            app.screen.query_one("#job-ram", Input).value = "nan"
            app.screen.query_one("#check-job").press()
            await pilot.pause()
            self.assertIn("non-negative", str(app.screen.query_one("#job-error", Static).render()))
            app.screen.query_one("#job-ram", Input).value = "40"
            app.screen.query_one("#check-job").press()
            await pilot.pause()
            results = str(app.screen.query_one("#job-results", Static).render())
            self.assertIn("My laptop", results)
            self.assertIn("BLOCKED", results)
            self.assertIn("iPad Air", results)
            await pilot.press("escape")
            self.assertIsNotNone(app.selected())

    async def test_failed_refresh_retains_cached_rows(self):
        app = DevicesApp()
        with patch.object(core, "refresh_device", side_effect=ValueError("Host unreachable")) as refresh:
            async with app.run_test(size=(90, 30)) as pilot:
                await pilot.press("r")
                await pilot.pause(.2)
                self.assertFalse(app.refreshing)
                self.assertEqual(app.query_one("#comparison", DataTable).row_count, 2)
                self.assertIn("Host unreachable", str(app.query_one("#status", Static).render()))
                refresh.assert_called_once()


if __name__ == "__main__":
    unittest.main()
