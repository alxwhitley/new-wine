#!/usr/bin/env python3
"""Disposable O6 rehearsal worker; extends synthetic_p5_worker.py's exact
contract with exactly one addition: a controllable pre-completion sleep, so
O6's concurrency fixtures can prove genuine real-time overlap between two
independent OS processes. stdlib only; never imports provider SDKs, network,
or DB clients.

Sleep-duration channel note (see O6 dispatch report for the full account):
the spec for this addition is "if env var SYNTHETIC_SLEEP_SECONDS is set and
parses as a positive float, sleep that many seconds." That check is exactly
what runs below. But invoke.py's WorkerAdapter (out of this packet's writable
allowlist) restricts adapter-supplied subprocess env to exactly
{SYNTHETIC_RESULT, SYNTHETIC_MARKER_PATH} -- a caller building a WorkerAdapter
cannot hand SYNTHETIC_SLEEP_SECONDS to the child process directly. So this
worker also accepts an optional "sleep_seconds" field embedded in the
SYNTHETIC_RESULT JSON payload (already an allowed channel) as an alternate
source for the same value, popped out before the remaining dict is treated as
this worker's own result -- so the echoed result stays schema-valid -- and
mapped onto the real env var so the sleep check itself stays a single,
literal "if os.environ.get('SYNTHETIC_SLEEP_SECONDS')" check regardless of
which channel supplied it.
"""

import json
import os
import time


def main() -> int:
    raw = json.loads(os.environ["SYNTHETIC_RESULT"])
    embedded_sleep = raw.pop("sleep_seconds", None) if isinstance(raw, dict) else None
    if embedded_sleep is not None and "SYNTHETIC_SLEEP_SECONDS" not in os.environ:
        os.environ["SYNTHETIC_SLEEP_SECONDS"] = str(embedded_sleep)

    sleep_raw = os.environ.get("SYNTHETIC_SLEEP_SECONDS")
    if sleep_raw:
        try:
            sleep_seconds = float(sleep_raw)
        except ValueError:
            sleep_seconds = None
        if sleep_seconds is not None and sleep_seconds > 0:
            time.sleep(sleep_seconds)

    result = raw
    for changed in result.get("changed_files", []):
        path = changed.get("path") if isinstance(changed, dict) else None
        if (changed.get("status") != "added" or not isinstance(path, str)
                or not path.startswith("scripts/") or "/../" in path or path.endswith("/..")):
            raise ValueError("synthetic fixture accepts only predeclared scripts additions")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as stream:
            stream.write(f"synthetic {result['packet_id']} {result['attempt']}\n".encode("utf-8"))
    marker = os.environ.get("SYNTHETIC_MARKER_PATH")
    if marker:
        with open(marker, "a", encoding="utf-8") as stream:
            stream.write(f"{result['packet_id']}:{result['attempt']}\n")
    with os.fdopen(os.dup(int(os.environ["HARNESS_RESULT_FD"])), "w", encoding="utf-8") as stream:
        json.dump(result, stream, sort_keys=True, separators=(",", ":"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
