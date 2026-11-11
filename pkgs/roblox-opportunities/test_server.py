"""Regression checks for the current Roblox chart API and durable refresh state."""
import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import server


class ChartTests(unittest.TestCase):
    def test_current_schema_uses_stable_id_and_preserves_chart_order(self):
        sorts = {"sorts": [
            {"sortId": "another-chart", "sortDisplayName": "Top Trending"},
            {"sortId": "top-trending", "sortDisplayName": "Trending renamed"},
        ]}
        content = {"sortDisplayName": "Trending renamed", "appliedFilters": "device=computer,age=all,country=all",
                   "games": [{"universeId": 2}, {"universeId": 1}, {"universeId": 2}]}
        details = {"data": [{"id": 1, "rootPlaceId": 11}, {"id": 2, "rootPlaceId": 22}]}
        with patch.object(server, "fetch", side_effect=[sorts, content, details]) as fetch:
            snapshot = server.chart_snapshot("trending")
        self.assertEqual(fetch.call_args_list[1].kwargs["sortId"], "top-trending")
        self.assertEqual(fetch.call_args_list[2].kwargs["universeIds"], "2,1")
        self.assertEqual(snapshot["chartId"], "top-trending")
        self.assertEqual(snapshot["chart"], "Trending renamed")
        self.assertEqual(snapshot["appliedFilters"], content["appliedFilters"])
        self.assertEqual([(row["id"], row["rank"]) for row in snapshot["games"]], [(2, 1), (1, 2)])

    def test_all_three_stable_chart_ids(self):
        for label, chart_id in server.CHART_IDS.items():
            with self.subTest(label=label), patch.object(server, "fetch", side_effect=[
                {"sorts": [{"sortId": chart_id, "sortDisplayName": label}]},
                {"games": [{"universeId": 5}]},
                {"data": [{"id": 5, "rootPlaceId": 55}]},
            ]):
                self.assertEqual(server.chart_snapshot(label)["chartId"], chart_id)

    def test_legacy_display_name_remains_supported(self):
        with patch.object(server, "fetch", side_effect=[
            {"sorts": [{"id": "legacy-trending", "displayName": "Top Trending"}]},
            {"games": [{"universeId": 5}]},
            {"data": [{"id": 5, "rootPlaceId": 55}]},
        ]):
            self.assertEqual(server.chart_snapshot("trending")["chart"], "Top Trending")

    def test_empty_or_unmatched_experiences_are_rejected(self):
        responses = [
            [{"sorts": []}],
            [{"sorts": [{"sortId": "top-trending"}]}, {"games": []}],
            [{"sorts": [{"sortId": "top-trending"}]}, {"games": [{"universeId": 5}]}, {"data": []}],
            [{"sorts": [{"sortId": "top-trending"}]}, {"games": [{"universeId": 5}]},
             {"data": [{"id": 8, "rootPlaceId": 88}]}],
        ]
        for result in responses:
            with self.subTest(result=result), patch.object(server, "fetch", side_effect=result):
                with self.assertRaises(ValueError):
                    server.chart_snapshot("trending")


class QuietHandler(server.Handler):
    def log_message(self, *_args):
        pass


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db = Path(self.directory.name) / "board.sqlite3"
        self.board = [{"id": "edited", "name": "Existing ranked idea", "notes": "Keep these edits"}]
        self.saved = {"chart": "Top Trending", "games": [{"id": 5}], "time": "2026-11-01T12:00:00Z"}
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute("CREATE TABLE board(id INTEGER PRIMARY KEY, body TEXT, revision INTEGER)")
            db.execute("CREATE TABLE snapshots(id INTEGER PRIMARY KEY, body TEXT)")
            db.execute("INSERT INTO board VALUES(1, ?, 7)", (json.dumps(self.board),))
            db.execute("INSERT INTO snapshots(body) VALUES(?)", (json.dumps(self.saved),))
        self.db_patch = patch.object(server, "DB", self.db, create=True)
        self.db_patch.start()
        self.http = server.ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.http.server_port}"

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=2)
        self.db_patch.stop()
        self.directory.cleanup()

    def refresh(self):
        request = Request(self.base + "/api/refresh", data=b'{"chart":"trending"}',
                          headers={"Content-Type": "application/json"})
        try:
            response = urlopen(request, timeout=3)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def test_failed_refresh_preserves_prior_snapshot_and_board(self):
        for error, expected in [(OSError("Upstream temporarily unavailable"), 502), (ValueError("No games"), 400)]:
            with self.subTest(error=error), patch.object(server, "chart_snapshot", side_effect=error):
                status, payload = self.refresh()
            self.assertEqual(status, expected)
            self.assertIn("error", payload)
            with urlopen(self.base + "/api/board", timeout=3) as response:
                board = json.load(response)
            self.assertEqual(board["ideas"], self.board)
            self.assertEqual(board["revision"], 7)
            self.assertEqual(board["snapshots"][0], self.saved)
            with closing(sqlite3.connect(self.db)) as db, db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0], 1)

    def test_successful_refresh_appends_snapshot_without_changing_board(self):
        new = dict(self.saved, time="2026-11-11T12:00:00Z", chartId="top-trending")
        with patch.object(server, "chart_snapshot", return_value=new):
            self.assertEqual(self.refresh(), (200, new))
        with closing(sqlite3.connect(self.db)) as db, db:
            self.assertEqual(db.execute("SELECT body, revision FROM board").fetchone(), (json.dumps(self.board), 7))
            self.assertEqual([json.loads(row[0]) for row in db.execute("SELECT body FROM snapshots ORDER BY id")],
                             [self.saved, new])

    def test_health_checks_persistent_board(self):
        with urlopen(self.base + "/api/health", timeout=3) as response:
            self.assertEqual(json.load(response), {"ok": True})
        with closing(sqlite3.connect(self.db)) as db, db:
            db.execute("DELETE FROM board")
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.base + "/api/health", timeout=3)
        self.assertEqual(caught.exception.code, 503)

    def test_requests_close_database_connections_after_reads_and_commits(self):
        connect = sqlite3.connect
        connections = []

        def tracked_connect(*args, **kwargs):
            connection = connect(*args, **kwargs)
            connections.append(connection)
            return connection

        with patch.object(server.sqlite3, "connect", side_effect=tracked_connect):
            for path in ("/api/health", "/api/board"):
                with urlopen(self.base + path, timeout=3) as response:
                    self.assertEqual(response.status, 200)
            with patch.object(server, "chart_snapshot", return_value=self.saved):
                self.assertEqual(self.refresh()[0], 200)
            request = Request(self.base + "/api/ideas",
                              data=json.dumps({"ideas": self.board, "revision": 7}).encode(),
                              headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=3) as response:
                self.assertEqual(json.load(response), {"revision": 8})
        self.assertEqual(len(connections), 4)
        for connection in connections:
            with self.assertRaises(sqlite3.ProgrammingError):
                connection.execute("SELECT 1")


if __name__ == "__main__":
    unittest.main()
