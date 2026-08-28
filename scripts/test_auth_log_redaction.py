#!/usr/bin/env python3
"""Regression test: a failed JWT decode must never write any bytes of the
bearer token itself into the logs.

Packet 4, Task 4.4 of the 2026-08-28 back-to-back completion queue.
backend/app/auth.py::get_optional_user() used to log `token[:20]` on every
decode failure -- removed this session. This proves it stays removed by
capturing the real log output of a real failed decode and asserting the
token substring never appears in it, rather than just reading the source.

No live network call: the token used is not even structurally a JWT, so
PyJWKClient fails at the unverified-header-decode step, before any JWKS
fetch would occur.

Run: python3 scripts/test_auth_log_redaction.py
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from types import SimpleNamespace

_SCRIPTS = Path(__file__).resolve().parent
_BACKEND = _SCRIPTS.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

os.environ.setdefault("SUPABASE_JWT_JWKS_URL", "https://example.invalid/.well-known/jwks.json")
os.environ.setdefault("SUPABASE_URL", "https://example.invalid")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "dummy-service-key")

from app import auth  # noqa: E402

failures = []


def _check(label: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    print("  [%s] %s" % (status, label))
    if not condition:
        failures.append(label)


class _CapturingHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(self.format(record))


def _fake_request(bearer_token: str):
    return SimpleNamespace(headers={"authorization": "Bearer %s" % bearer_token})


def main() -> int:
    print("=" * 78)
    print("A malformed bearer token never appears in the auth failure log")
    print("=" * 78)

    # Distinctive, unmistakably-a-token-not-english substring -- if this
    # string shows up anywhere in the captured log text, the redaction
    # regressed.
    fake_token = "not-a-real-jwt-QzXk9pLmWvT2c8Rn7yBhFj4Ae1Ds6Gu0"

    handler = _CapturingHandler()
    handler.setLevel(logging.WARNING)
    auth.logger.addHandler(handler)
    auth.logger.setLevel(logging.WARNING)
    try:
        result = auth.get_optional_user(_fake_request(fake_token))
    finally:
        auth.logger.removeHandler(handler)

    _check("decode failed as expected (returns None, doesn't raise)", result is None)
    _check("at least one warning was logged", len(handler.records) >= 1)
    combined = "\n".join(handler.records)
    _check(
        "the raw token never appears anywhere in the captured log output",
        fake_token not in combined,
    )
    _check(
        "no 'token prefix' phrasing survives either (the old log shape)",
        "token prefix" not in combined,
    )

    print()
    if failures:
        print("FAILED (%d):" % len(failures))
        for f in failures:
            print("  -", f)
        return 1
    print("All auth log redaction checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
