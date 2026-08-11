#!/usr/bin/env python3
"""Disposable P5 commissioning worker; never imports provider SDKs."""

import json
import os


def main() -> int:
    result = json.loads(os.environ["SYNTHETIC_RESULT"])
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
