from typing import Dict, List

from .checker import CheckResult


def _table(headers, rows) -> str:
    widths = [max(len(str(row[i])) for row in rows + [headers]) for i in range(len(headers))]
    lines = ["  ".join(str(h).ljust(w) for h, w in zip(headers, widths)).rstrip()]
    for row in rows:
        lines.append("  ".join(str(c).ljust(w) for c, w in zip(row, widths)).rstrip())
    return "\n".join(lines)


def render_results(results: List[CheckResult]) -> str:
    headers = ("STATE", "NAME", "CODE", "TIME", "DETAIL")
    rows = [
        (
            "UP" if r.ok else "DOWN",
            r.name,
            r.status if r.status is not None else "-",
            f"{r.latency_ms:.0f} ms",
            r.error or "",
        )
        for r in results
    ]
    return _table(headers, rows)


def _ms(value) -> str:
    return "-" if value is None else f"{value:.0f} ms"


def render_report(report: List[Dict[str, object]], hours: float) -> str:
    if not report:
        return f"no checks recorded in the last {hours:g} hours"

    headers = ("NAME", "UPTIME", "CHECKS", "FAILED", "OUTAGES", "AVG", "P95", "NOW")
    rows = [
        (
            item["name"],
            f"{item['uptime']:.2f}%",
            item["checks"],
            item["failures"],
            item["outages"],
            _ms(item["avg_ms"]),
            _ms(item["p95_ms"]),
            "up" if item["last_ok"] else "DOWN",
        )
        for item in report
    ]
    return f"Report for the last {hours:g} hours\n\n" + _table(headers, rows)


def render_history(rows) -> str:
    if not rows:
        return "no history for that target"
    headers = ("WHEN (UTC)", "STATE", "CODE", "TIME", "DETAIL")
    table_rows = [
        (
            r["checked_at"],
            "UP" if r["ok"] else "DOWN",
            r["status"] if r["status"] is not None else "-",
            f"{r['latency_ms']:.0f} ms",
            r["error"] or "",
        )
        for r in rows
    ]
    return _table(headers, table_rows)
