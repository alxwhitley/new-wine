#!/usr/bin/env python3
"""Unit tests for backend/app/services/search_analytics/subject_key.py.

Run: python3.12 scripts/test_analytics_subject_key.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

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


def main() -> int:
    from app.services.search_analytics import subject_key as sk

    with patch.dict(os.environ, {"ANALYTICS_HMAC_SECRET_V1": "test-secret-one"}, clear=False):
        key_a = sk.derive_subject_key("00000000-0000-0000-0000-000000000001", 1)
        key_a_again = sk.derive_subject_key("00000000-0000-0000-0000-000000000001", 1)
        key_b = sk.derive_subject_key("00000000-0000-0000-0000-000000000002", 1)

        check("derivation is deterministic for the same user+version", key_a == key_a_again)
        check("different users produce different keys", key_a != key_b)
        check("key is a hex string, not the raw user_id", "0000" not in key_a)
        check("key has sha256 hex length (64 chars)", len(key_a) == 64)

    with patch.dict(
        os.environ,
        {"ANALYTICS_HMAC_SECRET_V1": "test-secret-one", "ANALYTICS_HMAC_SECRET_V2": "test-secret-two"},
        clear=False,
    ):
        key_v1 = sk.derive_subject_key("00000000-0000-0000-0000-000000000001", 1)
        key_v2 = sk.derive_subject_key("00000000-0000-0000-0000-000000000001", 2)
        check("different secret versions produce different keys for the same user", key_v1 != key_v2)

    with patch.dict(os.environ, {}, clear=True):
        raised = False
        try:
            sk.derive_subject_key("00000000-0000-0000-0000-000000000001", 1)
        except sk.MissingHmacSecretError:
            raised = True
        check("missing secret env var raises MissingHmacSecretError, never derives a weak fallback", raised)

    check("CURRENT_SUBJECT_KEY_VERSION is defined and is an int", isinstance(sk.CURRENT_SUBJECT_KEY_VERSION, int))

    print("\n%d passed, %d failed" % (_pass, _fail))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
