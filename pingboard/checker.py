import socket
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from .config import Target

USER_AGENT = "pingboard/0.1"
MAX_BODY_BYTES = 1024 * 1024


@dataclass
class CheckResult:
    name: str
    url: str
    checked_at: str
    ok: bool
    status: Optional[int]
    latency_ms: float
    error: Optional[str] = None


def _describe(reason) -> str:
    if isinstance(reason, (socket.timeout, TimeoutError)):
        return "timeout"
    text = str(reason)
    return text if text else reason.__class__.__name__


def check_target(target: Target) -> CheckResult:
    request = urllib.request.Request(target.url, headers={"User-Agent": USER_AGENT})
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    started = time.perf_counter()

    status = None
    error = None
    body = None

    try:
        with urllib.request.urlopen(request, timeout=target.timeout) as response:
            status = response.status
            if target.contains is not None:
                body = response.read(MAX_BODY_BYTES).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status = exc.code
    except urllib.error.URLError as exc:
        error = _describe(exc.reason)
    except (socket.timeout, TimeoutError):
        error = "timeout"
    except OSError as exc:
        error = _describe(exc)

    latency_ms = round((time.perf_counter() - started) * 1000, 1)

    if error is None and status != target.expected_status:
        error = f"expected {target.expected_status}, got {status}"
    if error is None and target.contains is not None and target.contains not in (body or ""):
        error = f"text not found: {target.contains!r}"

    return CheckResult(
        name=target.name,
        url=target.url,
        checked_at=checked_at,
        ok=error is None,
        status=status,
        latency_ms=latency_ms,
        error=error,
    )


def check_all(targets: List[Target], workers: int = 8) -> List[CheckResult]:
    if not targets:
        return []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(targets)))) as pool:
        return list(pool.map(check_target, targets))
