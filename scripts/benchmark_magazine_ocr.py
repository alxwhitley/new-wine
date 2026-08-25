#!/usr/bin/env python3
"""Run or safely preflight a named, blind New Wine OCR benchmark manifest."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from magazine_review.benchmark import OCRProvider, dry_run_benchmark, run_benchmark


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify the named fixture hashes and emit no-call blind metadata.",
    )
    return parser


def main(argv: Sequence[str] | None = None, *, providers: Sequence[OCRProvider] | None = None) -> int:
    """Execute only caller-injected providers; no SDK, credential, or network setup occurs here."""
    args = _parser().parse_args(argv)
    if providers is None:
        raise RuntimeError("OCR providers must be supplied by the attended caller")
    if args.dry_run:
        dry_run_benchmark(args.manifest, providers, args.output)
    else:
        run_benchmark(args.manifest, providers, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
