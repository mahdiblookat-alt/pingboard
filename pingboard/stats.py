import math
from typing import List, Optional, Sequence


def percentile(values: Sequence[float], pct: float) -> Optional[float]:
    """Nearest-rank percentile. Returns None for an empty sequence."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]


def mean(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


def uptime_percent(ok_count: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round(100 * ok_count / total, 2)


def downtime_streaks(flags: List[bool]) -> int:
    """Number of separate runs of failures in a chronological list of ok flags."""
    streaks = 0
    previous_ok = True
    for ok in flags:
        if not ok and previous_ok:
            streaks += 1
        previous_ok = ok
    return streaks
