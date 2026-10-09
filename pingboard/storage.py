import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .checker import CheckResult
from .stats import downtime_streaks, mean, percentile, uptime_percent

SCHEMA = """
CREATE TABLE IF NOT EXISTS checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    ok INTEGER NOT NULL,
    status INTEGER,
    latency_ms REAL NOT NULL,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_checks_name_time ON checks (name, checked_at);
"""


class HistoryStore:
    def __init__(self, path) -> None:
        self.path = Path(path)
        if str(self.path) != ":memory:" and self.path.parent != Path("."):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def record_many(self, results: List[CheckResult]) -> None:
        self.conn.executemany(
            "INSERT INTO checks (name, url, checked_at, ok, status, latency_ms, error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (r.name, r.url, r.checked_at, int(r.ok), r.status, r.latency_ms, r.error)
                for r in results
            ],
        )
        self.conn.commit()

    def last_result(self, name: str) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM checks WHERE name = ? ORDER BY id DESC LIMIT 1", (name,)
        ).fetchone()

    def history(self, name: str, limit: int = 20) -> List[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM checks WHERE name = ? ORDER BY id DESC LIMIT ?",
            (name, limit),
        ).fetchall()

    def summary(self, hours: float = 24, now: Optional[datetime] = None) -> List[Dict[str, object]]:
        now = now or datetime.now(timezone.utc)
        since = (now - timedelta(hours=hours)).isoformat(timespec="seconds")

        rows = self.conn.execute(
            "SELECT * FROM checks WHERE checked_at >= ? ORDER BY name, id", (since,)
        ).fetchall()

        grouped: Dict[str, List[sqlite3.Row]] = {}
        for row in rows:
            grouped.setdefault(row["name"], []).append(row)

        report = []
        for name, items in grouped.items():
            flags = [bool(r["ok"]) for r in items]
            latencies = [r["latency_ms"] for r in items if r["status"] is not None]
            avg = mean(latencies)
            p95 = percentile(latencies, 95)
            last = items[-1]
            report.append(
                {
                    "name": name,
                    "checks": len(items),
                    "failures": flags.count(False),
                    "outages": downtime_streaks(flags),
                    "uptime": uptime_percent(flags.count(True), len(flags)),
                    "avg_ms": round(avg, 1) if avg is not None else None,
                    "p95_ms": round(p95, 1) if p95 is not None else None,
                    "last_ok": bool(last["ok"]),
                    "last_checked": last["checked_at"],
                }
            )
        return report
