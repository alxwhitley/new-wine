#!/usr/bin/env python3
"""Drift gate: backend/app/constants.py's VALID_TAGS must exactly match
scripts/taxonomy.py's VALID_TAGS (the canonical source, CLAUDE.md).

Run: python3.12 scripts/test_taxonomy_backend_sync.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

_pass = 0
_fail = 0


def check(label: str, condition: bool) -> None:
    global _pass, _fail
    print("  [%s] %s" % ("PASS" if condition else "FAIL", label))
    if condition:
        _pass += 1
    else:
        _fail += 1


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    taxonomy = _load_module("scripts_taxonomy", ROOT / "scripts" / "taxonomy.py")
    from app.constants import VALID_TAGS as backend_tags  # noqa: E402

    canonical = taxonomy.VALID_TAGS
    check("backend VALID_TAGS has the same count as scripts/taxonomy.py",
          len(backend_tags) == len(canonical))
    missing_from_backend = canonical - backend_tags
    extra_in_backend = backend_tags - canonical
    check("no tags missing from backend/app/constants.py",
          missing_from_backend == set())
    check("no extra tags in backend/app/constants.py not in scripts/taxonomy.py",
          extra_in_backend == set())
    if missing_from_backend:
        print("    missing:", sorted(missing_from_backend))
    if extra_in_backend:
        print("    extra:", sorted(extra_in_backend))

    print("\n%d passed, %d failed" % (_pass, _fail))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
