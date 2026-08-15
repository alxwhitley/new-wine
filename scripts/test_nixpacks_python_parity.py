#!/usr/bin/env python3
"""
Guards manifest-vs-manifest drift between the two Nixpacks build manifests
that must agree on Python interpreter version:

  - backend/nixpacks.toml     (backend web service, Railway Root Directory
    "backend" -- see CLAUDE.md Invariant 1 / Tech Stack)
  - nixpacks.toml (repo root) (async answer worker service, Railway Root
    Directory "/" -- see CLAUDE.md's "The repo-root nixpacks.toml is the
    async worker service's build manifest" Landmine entry, which states
    the intended parity: "same interpreter: python312")

This script does NOT check either manifest against CLAUDE.md's own
documentation (which currently says Python 3.9 in Invariant 1 and the
Tech Stack table -- stale as of commit a729fba, 2026-06-12, which moved
both manifests to python312; see the accompanying audit note,
docs/audits/nixpacks_python_parity_2026-08-14.md, for that finding). This
script's only job is to catch the two live manifests disagreeing WITH
EACH OTHER going forward -- e.g. if a future change bumps one service to
a newer Python without bumping the other, breaking the documented parity
and potentially the worker's `pip install -r backend/requirements.txt`
step if wheels differ across versions.

Deliberately stdlib-only, no third-party dependency, and deliberately NOT
using Python 3.11+'s built-in `tomllib` -- this dev machine's own local
`python3` is 3.9.6 (verified via `python3 --version`), and `tomllib` is not
importable there. A simple regex/line-scan against the well-known, narrow
`nixPkgs = [...]` line format is used instead, matching this repo's other
`scripts/test_*.py` convention (a standalone runnable script, not pytest).

Run from the repo root: python3 scripts/test_nixpacks_python_parity.py
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

BACKEND_MANIFEST = REPO_ROOT / "backend" / "nixpacks.toml"
ROOT_MANIFEST = REPO_ROOT / "nixpacks.toml"

# Matches a line like: nixPkgs = ["python312"]  (single or double quotes,
# optional extra packages in the list, arbitrary internal whitespace).
# Captures the FIRST quoted token that looks like a pythonNN interpreter
# name -- that's the only thing this check cares about; other nixPkgs
# entries (if any are ever added) are ignored.
NIXPKGS_LINE_RE = re.compile(r'^\s*nixPkgs\s*=\s*\[(?P<list>[^\]]*)\]', re.MULTILINE)
PYTHON_PKG_RE = re.compile(r'["\'](?P<pkg>python\d+)["\']')


def extract_python_version(manifest_path):
    """Read a nixpacks.toml file and return its declared pythonNN nixPkgs
    entry as a string (e.g. "python312"), or None if the file has no
    nixPkgs line or no python package in it."""
    text = manifest_path.read_text()
    match = NIXPKGS_LINE_RE.search(text)
    if not match:
        return None
    pkg_match = PYTHON_PKG_RE.search(match.group("list"))
    if not pkg_match:
        return None
    return pkg_match.group("pkg")


def main():
    failures = []

    if not BACKEND_MANIFEST.is_file():
        failures.append("missing file: %s" % BACKEND_MANIFEST)
    if not ROOT_MANIFEST.is_file():
        failures.append("missing file: %s" % ROOT_MANIFEST)

    if failures:
        print("FAIL: %s" % "; ".join(failures))
        return 1

    backend_version = extract_python_version(BACKEND_MANIFEST)
    root_version = extract_python_version(ROOT_MANIFEST)

    print("backend/nixpacks.toml declares: %s" % backend_version)
    print("nixpacks.toml (repo root) declares: %s" % root_version)

    if backend_version is None:
        failures.append(
            "could not find a nixPkgs python entry in %s" % BACKEND_MANIFEST
        )
    if root_version is None:
        failures.append(
            "could not find a nixPkgs python entry in %s" % ROOT_MANIFEST
        )

    if not failures and backend_version != root_version:
        failures.append(
            "Python version MISMATCH between manifests: "
            "backend/nixpacks.toml=%s vs nixpacks.toml=%s "
            "(these two services are documented as needing to match -- see "
            "CLAUDE.md's repo-root nixpacks.toml Landmine entry, "
            '"same interpreter: python312")' % (backend_version, root_version)
        )

    print()
    if failures:
        print("%d check(s) FAILED:" % len(failures))
        for f in failures:
            print("  -", f)
        return 1

    print("PASS: backend/nixpacks.toml and nixpacks.toml agree (%s)." % backend_version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
