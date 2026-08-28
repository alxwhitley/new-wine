#!/usr/bin/env python3
"""Unit tests for backend/app/services/search_analytics/redaction.py.

Run: python3.12 scripts/test_analytics_redaction.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

_pass = 0
_fail = 0


def check(label: str, condition: bool, detail: str = None) -> None:
    global _pass, _fail
    print("  [%s] %s" % ("PASS" if condition else "FAIL", label))
    if detail:
        print("         %s" % detail)
    if condition:
        _pass += 1
    else:
        _fail += 1


def main() -> int:
    from app.services.search_analytics.redaction import redact_question, REDACTION_VERSION

    r = redact_question("Is my email jane.doe@example.com safe to give my pastor?")
    check("email is stripped", "jane.doe@example.com" not in (r.text or ""), r.text)
    check("status is redacted", r.status == "redacted")

    r = redact_question("Can you call me at (555) 867-5309 about deliverance?")
    check("phone number is stripped", "867-5309" not in (r.text or ""), r.text)

    r = redact_question("I live at 742 Evergreen Terrace, is that relevant to healing prayer?")
    check("street address is stripped", "742 Evergreen Terrace" not in (r.text or ""), r.text)

    r = redact_question("My account id is 3fa85f64-5717-4562-b3fc-2c963f66afa6, why no material on tongues?")
    check("uuid-shaped account identifier is stripped",
          "3fa85f64-5717-4562-b3fc-2c963f66afa6" not in (r.text or ""), r.text)

    r = redact_question("Reach me from 192.168.1.100 or 2001:db8::1 about prophecy")
    check("ipv4 is stripped", "192.168.1.100" not in (r.text or ""), r.text)
    check("ipv6 is stripped", "2001:db8::1" not in (r.text or ""), r.text)

    r = redact_question("What did Derek Prince teach about the baptism of the Holy Spirit?")
    check("teacher name Derek Prince is NOT stripped", "Derek Prince" in (r.text or ""), r.text)
    check("biblical concept baptism of the Holy Spirit is NOT stripped",
          "baptism of the Holy Spirit" in (r.text or ""), r.text)

    long_question = "What does the corpus say about deliverance " + ("and warfare " * 200)
    r = redact_question(long_question)
    check("stored length is capped at 500 chars", len(r.text or "") <= 500)

    check("REDACTION_VERSION is a non-empty string", isinstance(REDACTION_VERSION, str) and len(REDACTION_VERSION) > 0)

    print("\n%d passed, %d failed" % (_pass, _fail))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
