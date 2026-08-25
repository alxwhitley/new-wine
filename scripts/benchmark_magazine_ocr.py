#!/usr/bin/env python3
"""Run or safely preflight a named, blind New Wine OCR benchmark manifest."""

from __future__ import annotations

import argparse
import importlib
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Callable, Mapping

from magazine_review.benchmark import OCRProvider, dry_run_benchmark, run_benchmark


PROVIDER_FACTORY_ENV = "MAGAZINE_OCR_BENCHMARK_PROVIDER_FACTORY"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify the named fixture hashes and emit no-call blind metadata.",
    )
    parser.add_argument(
        "--provider-adapter-factory",
        help=(
            "Import path module:function returning exactly three OCR providers; "
            "may also be set with " + PROVIDER_FACTORY_ENV
        ),
    )
    return parser


def _import_factory(spec: str) -> Callable[[Path], object]:
    module_name, separator, attribute = spec.partition(":")
    if not separator or not module_name or not attribute:
        raise RuntimeError("provider_adapter_factory_invalid")
    try:
        factory = getattr(importlib.import_module(module_name), attribute)
    except (ImportError, AttributeError) as exc:
        raise RuntimeError("provider_adapter_factory_import_failed") from exc
    if not callable(factory):
        raise RuntimeError("provider_adapter_factory_invalid")
    return factory


def _factory_providers(value: object) -> Sequence[OCRProvider]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise RuntimeError("provider_adapter_factory_result_invalid")
    return value


def main(
    argv: Sequence[str] | None = None,
    *,
    providers: Sequence[OCRProvider] | None = None,
    provider_factory: Callable[[Path], object] | None = None,
    environ: Mapping[str, str] | None = None,
) -> int:
    """Run injected providers or an explicitly configured attended factory."""
    args = _parser().parse_args(argv)
    if providers is None:
        factory = provider_factory
        if factory is None:
            environment = os.environ if environ is None else environ
            factory_spec = args.provider_adapter_factory or environment.get(
                PROVIDER_FACTORY_ENV
            )
            if not factory_spec:
                raise RuntimeError("provider_adapter_factory_required")
            factory = _import_factory(factory_spec)
        providers = _factory_providers(factory(args.manifest))
    if args.dry_run:
        dry_run_benchmark(args.manifest, providers, args.output)
    else:
        run_benchmark(args.manifest, providers, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
