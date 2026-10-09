# pingboard

A tiny uptime monitor. Point it at a list of URLs, and it checks them in parallel, stores every result in a local SQLite file, tells you when something goes down or comes back, and can print uptime and latency reports from the stored history. Standard library only.

## Install

```bash
git clone https://github.com/<mahdiblookat-alt>/pingboard.git
cd pingboard
pip install -e .
```

Or run it in place with `python -m pingboard`.

## Quick start

```bash
pingboard init            # writes pingboard.json
pingboard check           # run every check once
pingboard watch -i 30     # keep checking every 30 seconds
pingboard report          # uptime and latency for the last 24 hours
pingboard history example # recent checks for one target
```

`check` exits with code 0 when everything is up and 2 when at least one target failed, so it also works in cron jobs and CI.

## Config

```json
{
  "targets": [
    { "name": "website", "url": "https://example.com", "contains": "Example Domain" },
    { "name": "health", "url": "https://api.example.com/health", "timeout": 3 },
    { "name": "old-redirect", "url": "https://example.com/old", "expected_status": 200 }
  ]
}
```

| Field | Default | Meaning |
| --- | --- | --- |
| `name` | required | unique label |
| `url` | required | `http://` or `https://` address |
| `expected_status` | `200` | status code that counts as healthy |
| `timeout` | `5` | seconds before the check gives up |
| `contains` | none | text that must appear in the response body |

Redirects are followed, so `expected_status` applies to the final response.

## Example session

```
$ pingboard check
STATE  NAME          CODE  TIME   DETAIL
UP     local-site    200   66 ms
DOWN   missing-page  404   64 ms  expected 200, got 404
DOWN   closed-port   -     65 ms  [Errno 111] Connection refused

$ pingboard report
Report for the last 24 hours

NAME          UPTIME   CHECKS  FAILED  OUTAGES  AVG    P95    NOW
closed-port   0.00%    2       2       1        -      -      DOWN
local-site    100.00%  2       0       0        72 ms  77 ms  up
missing-page  0.00%    2       2       1        59 ms  64 ms  DOWN
```

While `watch` is running, state changes are printed as they happen:

```
!! DOWN       website: timeout
!! RECOVERED  website
```

## Options

```
pingboard check   [-c CONFIG] [--db FILE] [-w WORKERS]
pingboard watch   [-c CONFIG] [--db FILE] [-i SECONDS] [-n ROUNDS] [-w WORKERS]
pingboard report  [--db FILE] [--hours N]
pingboard history NAME [--db FILE] [--limit N]
```

The defaults are `pingboard.json` for the config and `pingboard.db` for the history, both in the current directory.

## Tests

The tests start a throwaway HTTP server on localhost, so they need no network access.

```bash
python -m unittest discover -s tests -v
```

## Layout

```
pingboard/
    config.py    config loading and validation
    checker.py   single check and parallel runner
    storage.py   SQLite history and summaries
    stats.py     percentile, mean, uptime helpers
    monitor.py   run once, watch loop, state change detection
    render.py    table output
    cli.py       command line entry point
tests/
    test_pingboard.py
```

## License

MIT
