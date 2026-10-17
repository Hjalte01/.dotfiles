import importlib.util
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "pdfpick", Path(__file__).resolve().parents[1] / "scripts/pdfpick.py")
pdfpick = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pdfpick)


class PdfpickTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        env = {"HOME": str(self.home), "XDG_DATA_HOME": str(self.home / "data"),
               "XDG_STATE_HOME": str(self.home / "state"),
               "XDG_CONFIG_HOME": str(self.home / "config")}
        self.environment = patch.dict(os.environ, env)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def file(self, relative, contents=b"%PDF-test"):
        path = self.home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        return path

    def native_history(self, rows):
        database = self.home / "data/zathura/bookmarks.sqlite"
        database.parent.mkdir(parents=True)
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute("CREATE TABLE fileinfo (file TEXT PRIMARY KEY, time TIMESTAMP)")
            connection.executemany("INSERT INTO fileinfo VALUES (?, ?)", rows)
        return database

    def test_native_history_is_read_only_and_merges_with_immediate_opens(self):
        paper = self.file("Downloads/paper.pdf")
        older = self.file("Documents/old.pdf")
        database = self.native_history([
            (str(paper), "2026-01-01 12:00:00"),
            (str(older), "2025-01-01 12:00:00"),
        ])
        original = database.read_bytes()
        self.assertEqual(pdfpick.history()[str(paper)], 1767268800)
        with patch.object(pdfpick.time, "time", return_value=1800000000):
            pdfpick.record_opened([str(paper)])
        self.assertEqual(pdfpick.history()[str(paper)], 1800000000)
        self.assertIn(str(older), pdfpick.history())
        self.assertEqual(database.read_bytes(), original)
        self.assertEqual((self.home / "state/pdfpick/history.sqlite").stat().st_mode & 0o777, 0o600)

    def test_missing_history_does_not_create_databases(self):
        self.assertEqual(pdfpick.history(), {})
        self.assertFalse((self.home / "data").exists())
        self.assertFalse((self.home / "state").exists())

    def test_pdf_scan_completion_filters_and_explicit_scope(self):
        root = self.home / "papers"
        normal = self.file("papers/ML/author's paper.PDF")
        unusual = self.file("papers/ML/a\tweird\nname.pdf")
        self.file("papers/partial.pdf")
        self.file("papers/partial.pdf.part")
        self.file("papers/empty.pdf", b"")
        self.file("papers/.hidden/secret.pdf")
        self.file("papers/target/generated.pdf")
        self.file("papers/image.png")
        outside = self.file("elsewhere/old.pdf")
        self.native_history([(str(outside), "2026-01-01 00:00:00")])
        entries = pdfpick.scan([root], include_history=False)
        self.assertEqual({e["path"] for e in entries}, {str(normal), str(unusual)})
        self.assertGreaterEqual(entries[0]["added"], normal.stat().st_ctime)
        self.assertIn(str(outside), {e["path"] for e in pdfpick.scan([root])})
        self.assertEqual(len(pdfpick.scan([root], include_hidden=True, include_history=False)), 4)

    def test_views_use_open_times_and_folder_boundaries(self):
        entries = [
            {"path": str(self.home / "Downloads/ML/first.pdf"), "added": 10},
            {"path": str(self.home / "Downloads/ML/second.pdf"), "added": 30},
            {"path": str(self.home / "Downloads/ML-other/third.pdf"), "added": 20},
            {"path": str(self.home / "Papers/fourth.pdf"), "added": 40},
        ]
        recent = {entries[0]["path"]: 100, entries[2]["path"]: 200}
        def names(view, folder=None):
            return [Path(e["path"]).name for e in pdfpick.view_entries(
                entries, view, folder, self.home / "Downloads", recent)]
        self.assertEqual(names("all"), ["fourth.pdf", "second.pdf", "third.pdf", "first.pdf"])
        self.assertEqual(names("downloads"), ["second.pdf", "third.pdf", "first.pdf"])
        self.assertEqual(names("opened"), ["third.pdf", "first.pdf"])
        self.assertEqual(names("all", self.home / "Downloads/ML"), ["second.pdf", "first.pdf"])


if __name__ == "__main__":
    unittest.main()
