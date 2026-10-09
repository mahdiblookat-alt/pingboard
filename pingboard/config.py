import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

SAMPLE_CONFIG = {
    "targets": [
        {"name": "example", "url": "https://example.com", "contains": "Example Domain"},
        {"name": "httpbin-ok", "url": "https://httpbin.org/status/200"},
        {
            "name": "httpbin-teapot",
            "url": "https://httpbin.org/status/418",
            "expected_status": 418,
            "timeout": 8,
        },
    ]
}


class ConfigError(Exception):
    pass


@dataclass
class Target:
    name: str
    url: str
    expected_status: int = 200
    timeout: float = 5.0
    contains: Optional[str] = None


def _parse_target(raw: dict, index: int) -> Target:
    if not isinstance(raw, dict):
        raise ConfigError(f"target #{index} must be an object")

    name = str(raw.get("name", "")).strip()
    url = str(raw.get("url", "")).strip()
    if not name:
        raise ConfigError(f"target #{index} has no name")
    if urlparse(url).scheme not in ("http", "https"):
        raise ConfigError(f"target {name!r}: url must start with http:// or https://")

    try:
        expected = int(raw.get("expected_status", 200))
        timeout = float(raw.get("timeout", 5.0))
    except (TypeError, ValueError):
        raise ConfigError(f"target {name!r}: expected_status and timeout must be numbers") from None
    if timeout <= 0:
        raise ConfigError(f"target {name!r}: timeout must be positive")

    return Target(
        name=name,
        url=url,
        expected_status=expected,
        timeout=timeout,
        contains=raw.get("contains"),
    )


def load_targets(path) -> List[Target]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON in {path}: {exc}") from None

    raw_targets = data.get("targets") if isinstance(data, dict) else None
    if not raw_targets:
        raise ConfigError("config must contain a non-empty 'targets' list")

    targets = [_parse_target(raw, i + 1) for i, raw in enumerate(raw_targets)]
    names = [t.name for t in targets]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise ConfigError(f"duplicate target names: {', '.join(duplicates)}")
    return targets


def write_sample(path) -> None:
    target = Path(path)
    if target.exists():
        raise ConfigError(f"{path} already exists")
    target.write_text(json.dumps(SAMPLE_CONFIG, indent=2) + "\n", encoding="utf-8")
