#!/usr/bin/env python3
"""Disposable verdict-only reviewer fixture for P5 commissioning."""

import json
import sys


def main() -> int:
    verdict = json.load(sys.stdin)
    json.dump(verdict, sys.stdout, sort_keys=True, separators=(",", ":"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
