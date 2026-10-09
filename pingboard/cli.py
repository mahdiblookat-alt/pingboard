import argparse
import sys
from typing import List, Optional

from .config import ConfigError, load_targets, write_sample
from .monitor import run_once, watch
from .render import render_history, render_report, render_results
from .storage import HistoryStore

DEFAULT_CONFIG = "pingboard.json"
DEFAULT_DB = "pingboard.db"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pingboard", description="Tiny uptime monitor with history."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def common(cmd, with_config=True):
        if with_config:
            cmd.add_argument("-c", "--config", default=DEFAULT_CONFIG)
        cmd.add_argument("--db", default=DEFAULT_DB)

    init = sub.add_parser("init", help="write a sample config file")
    init.add_argument("path", nargs="?", default=DEFAULT_CONFIG)

    check = sub.add_parser("check", help="check every target once")
    common(check)
    check.add_argument("-w", "--workers", type=int, default=8)

    watch_cmd = sub.add_parser("watch", help="check on a loop")
    common(watch_cmd)
    watch_cmd.add_argument("-i", "--interval", type=float, default=60.0, help="seconds")
    watch_cmd.add_argument("-n", "--count", type=int, default=0, help="stop after N rounds")
    watch_cmd.add_argument("-w", "--workers", type=int, default=8)

    report = sub.add_parser("report", help="uptime and latency summary")
    common(report, with_config=False)
    report.add_argument("--hours", type=float, default=24.0)

    history = sub.add_parser("history", help="recent checks for one target")
    common(history, with_config=False)
    history.add_argument("name")
    history.add_argument("--limit", type=int, default=20)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        if args.command == "init":
            write_sample(args.path)
            print(f"wrote {args.path}")
            return 0

        store = HistoryStore(args.db)
        try:
            if args.command == "check":
                targets = load_targets(args.config)
                results, events = run_once(targets, store, args.workers)
                print(render_results(results))
                for event in events:
                    print(f"!! {event}")
                return 0 if all(r.ok for r in results) else 2

            if args.command == "watch":
                targets = load_targets(args.config)
                watch(targets, store, args.interval, args.count, args.workers)
                return 0

            if args.command == "report":
                print(render_report(store.summary(args.hours), args.hours))
                return 0

            print(render_history(store.history(args.name, args.limit)))
            return 0
        finally:
            store.close()
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
