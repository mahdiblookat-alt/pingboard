import time
from typing import Callable, List, Tuple

from .checker import CheckResult, check_all
from .config import Target
from .render import render_results
from .storage import HistoryStore


def run_once(
    targets: List[Target], store: HistoryStore, workers: int = 8
) -> Tuple[List[CheckResult], List[str]]:
    """Check every target, save the results and report state changes."""
    results = check_all(targets, workers)
    previous = {r.name: store.last_result(r.name) for r in results}
    store.record_many(results)

    events = []
    for result in results:
        before = previous[result.name]
        if before is None:
            continue
        if before["ok"] and not result.ok:
            events.append(f"DOWN       {result.name}: {result.error}")
        elif not before["ok"] and result.ok:
            events.append(f"RECOVERED  {result.name}")
    return results, events


def watch(
    targets: List[Target],
    store: HistoryStore,
    interval: float,
    count: int = 0,
    workers: int = 8,
    sleep: Callable[[float], None] = time.sleep,
    out: Callable[[str], None] = print,
) -> int:
    """Run checks repeatedly. A count of 0 means run until interrupted."""
    rounds = 0
    try:
        while True:
            results, events = run_once(targets, store, workers)
            stamp = results[0].checked_at if results else ""
            out(f"--- {stamp} ---")
            out(render_results(results))
            for event in events:
                out(f"!! {event}")

            rounds += 1
            if count and rounds >= count:
                break
            sleep(interval)
    except KeyboardInterrupt:
        out("stopped")
    return rounds
