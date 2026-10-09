import json
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pingboard.checker import CheckResult, check_all, check_target
from pingboard.config import ConfigError, Target, load_targets, write_sample
from pingboard.monitor import run_once, watch
from pingboard.stats import downtime_streaks, mean, percentile, uptime_percent
from pingboard.storage import HistoryStore


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/ok":
            self._reply(200, b"hello world")
        elif self.path == "/fail":
            self._reply(500, b"boom")
        elif self.path == "/flaky":
            self._reply(500 if Handler.broken else 200, b"state")
        elif self.path == "/slow":
            time.sleep(1.5)
            self._reply(200, b"late")
        else:
            self._reply(404, b"nope")

    def _reply(self, code, body):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


Handler.broken = False


class ServerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.server.daemon_threads = True
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def target(self, path, **kwargs):
        return Target(name=kwargs.pop("name", path.strip("/") or "root"), url=self.base + path, **kwargs)


class CheckerTests(ServerCase):
    def test_success(self):
        result = check_target(self.target("/ok"))
        self.assertTrue(result.ok)
        self.assertEqual(result.status, 200)
        self.assertIsNone(result.error)

    def test_wrong_status(self):
        result = check_target(self.target("/fail"))
        self.assertFalse(result.ok)
        self.assertEqual(result.status, 500)
        self.assertEqual(result.error, "expected 200, got 500")

    def test_expected_status_can_be_changed(self):
        self.assertTrue(check_target(self.target("/nothing", expected_status=404)).ok)

    def test_body_check(self):
        self.assertTrue(check_target(self.target("/ok", contains="hello")).ok)
        missing = check_target(self.target("/ok", contains="goodbye"))
        self.assertFalse(missing.ok)
        self.assertIn("text not found", missing.error)

    def test_timeout(self):
        result = check_target(self.target("/slow", timeout=0.3))
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "timeout")
        self.assertIsNone(result.status)

    def test_connection_refused(self):
        result = check_target(Target(name="dead", url="http://127.0.0.1:9", timeout=1))
        self.assertFalse(result.ok)
        self.assertIsNone(result.status)
        self.assertTrue(result.error)

    def test_check_all_keeps_order(self):
        targets = [self.target("/ok", name="a"), self.target("/fail", name="b"), self.target("/ok", name="c")]
        results = check_all(targets, workers=3)
        self.assertEqual([r.name for r in results], ["a", "b", "c"])
        self.assertEqual([r.ok for r in results], [True, False, True])


class MonitorTests(ServerCase):
    def setUp(self):
        self.store = HistoryStore(":memory:")
        Handler.broken = False

    def tearDown(self):
        self.store.close()

    def test_state_changes_are_reported(self):
        targets = [self.target("/flaky", name="flaky"), self.target("/ok", name="steady")]

        _, events = run_once(targets, self.store)
        self.assertEqual(events, [])

        Handler.broken = True
        _, events = run_once(targets, self.store)
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0].startswith("DOWN"))

        _, events = run_once(targets, self.store)
        self.assertEqual(events, [])

        Handler.broken = False
        _, events = run_once(targets, self.store)
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0].startswith("RECOVERED"))

    def test_watch_runs_requested_rounds(self):
        lines = []
        sleeps = []
        rounds = watch(
            [self.target("/ok")], self.store, interval=5, count=3,
            sleep=sleeps.append, out=lines.append,
        )
        self.assertEqual(rounds, 3)
        self.assertEqual(sleeps, [5, 5])
        self.assertEqual(len(self.store.history("ok", 10)), 3)


class StorageTests(unittest.TestCase):
    def make_result(self, name, ok, minutes_ago, latency=100.0, now=None):
        when = (now - timedelta(minutes=minutes_ago)).isoformat(timespec="seconds")
        return CheckResult(
            name=name, url="http://x", checked_at=when, ok=ok,
            status=200 if ok else None, latency_ms=latency,
            error=None if ok else "timeout",
        )

    def test_summary(self):
        now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
        store = HistoryStore(":memory:")
        store.record_many([
            self.make_result("site", True, 50, 100, now),
            self.make_result("site", False, 40, 0, now),
            self.make_result("site", False, 30, 0, now),
            self.make_result("site", True, 20, 300, now),
            self.make_result("old", True, 60 * 30, 100, now),
        ])

        report = store.summary(hours=24, now=now)
        self.assertEqual([r["name"] for r in report], ["site"])
        site = report[0]
        self.assertEqual(site["checks"], 4)
        self.assertEqual(site["failures"], 2)
        self.assertEqual(site["outages"], 1)
        self.assertEqual(site["uptime"], 50.0)
        self.assertEqual(site["avg_ms"], 200.0)
        self.assertTrue(site["last_ok"])
        store.close()


class StatsTests(unittest.TestCase):
    def test_percentile(self):
        values = list(range(1, 101))
        self.assertEqual(percentile(values, 95), 95)
        self.assertEqual(percentile(values, 50), 50)
        self.assertEqual(percentile([7], 99), 7)
        self.assertIsNone(percentile([], 95))

    def test_mean_and_uptime(self):
        self.assertEqual(mean([1, 2, 3]), 2)
        self.assertIsNone(mean([]))
        self.assertEqual(uptime_percent(1, 3), 33.33)
        self.assertEqual(uptime_percent(0, 0), 0.0)

    def test_streaks(self):
        self.assertEqual(downtime_streaks([True, False, False, True, False]), 2)
        self.assertEqual(downtime_streaks([True, True]), 0)
        self.assertEqual(downtime_streaks([False, True]), 1)


class ConfigTests(unittest.TestCase):
    def write(self, directory, payload):
        path = Path(directory) / "config.json"
        path.write_text(payload if isinstance(payload, str) else json.dumps(payload))
        return path

    def test_valid_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, {"targets": [
                {"name": "a", "url": "https://example.com", "timeout": 2, "contains": "x"},
                {"name": "b", "url": "http://localhost:8080", "expected_status": 204},
            ]})
            targets = load_targets(path)
        self.assertEqual(targets[0].timeout, 2.0)
        self.assertEqual(targets[0].contains, "x")
        self.assertEqual(targets[1].expected_status, 204)

    def test_invalid_configs(self):
        cases = [
            "not json",
            {"targets": []},
            {"targets": [{"name": "a", "url": "ftp://example.com"}]},
            {"targets": [{"url": "https://example.com"}]},
            {"targets": [{"name": "a", "url": "https://x.com", "timeout": 0}]},
            {"targets": [{"name": "a", "url": "https://x.com"}, {"name": "a", "url": "https://y.com"}]},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            for payload in cases:
                with self.subTest(payload=payload):
                    with self.assertRaises(ConfigError):
                        load_targets(self.write(tmp, payload))

    def test_missing_file(self):
        with self.assertRaises(ConfigError):
            load_targets("/definitely/not/here.json")

    def test_sample_config_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.json"
            write_sample(path)
            self.assertGreater(len(load_targets(path)), 0)
            with self.assertRaises(ConfigError):
                write_sample(path)


if __name__ == "__main__":
    unittest.main()
