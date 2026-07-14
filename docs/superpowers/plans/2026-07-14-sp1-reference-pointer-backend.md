# SP1 — Reference-Pointer Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** New chat answers generate a verified list of "this verse/teacher mention is real and safe to point to" data (`verified_references`), computed after the answer finishes streaming, with zero visible change to the answer itself and zero risk of a false-positive resolution.

**Architecture:** Two passes over one generation. Pass 1 (writer): Claude, in the same call that produces `<answer>`, also emits a new `<reference_mentions>` block listing every verse/teacher string it believes it used — a proposal, trusted for nothing except "check this." Pass 2 (verifier): pure, non-LLM Python code that (a) confirms each proposed string actually appears in the real answer text, (b) resolves it against real data (the `verses` table for scripture, the existing alias-normalization + license/visibility gate for teachers), and (c) for teachers, rejects a fixed list of biblical figures outright, independent of what the alias table says. Only what survives all three checks is attached to the existing final SSE `meta` event, as a new field the frontend does not yet read.

**Tech Stack:** Python 3.9 / FastAPI (existing `backend/app`), Anthropic Claude Sonnet 4.5 (existing answer-writing call), Supabase Python client (existing `get_supabase()`), no new dependencies.

## Global Constraints

- Fail-quiet, always: any single failed check anywhere in the chain (presence, resolution, biblical-figure backstop, servability) drops that one mention silently. No partial credit, no error surfaced to the user.
- Zero false resolutions is the acceptance bar for the whole feature — not a percentage target.
- The plain `<answer>` text the user reads must be byte-for-byte unaffected by anything added in this plan, including malformed model output in the new block.
- No visible UI change. The frontend is untouched by this plan; `verified_references` is a new, currently-unconsumed field.
- Out of scope (do not build): citation-to-source-passage opening, retrofitting old conversations, in-panel text-selection follow-ups, user-selectable translations, SP3 tool rows, anything in `chat-message.tsx` / `study-panel.tsx` / `lib/study-reference.ts`.
- Any DB schema change would go through the `migrations/` path with Alex's review — this plan does not require one (no new tables/columns; only reads existing `verses`, `sources`, `source_aliases`, `app_settings`).
- Reuse, never fork: verse parsing reuses `app.routers.study`'s existing code; teacher-name normalization reuses (after relocation) the same function `scripts/source_resolver.py` uses for ingest; the servability check reuses the exact predicate already live in migrations 049/056.
- If a user's question names a specific verse, the answer must explicitly name that verse back in its own text — otherwise there is nothing in the answer for the panel to ever underline for the very reference the user asked about. This is a writer instruction (Task 10), proven by a dedicated Track-A case (A7, Task 13).
- The system-prompt change (Task 10) is the one part of this plan that is not purely additive — it touches every answer, not just SP1's new block. Phase B is not complete until the answer-quality regression check (Tasks 9 + 12) confirms ordinary answers are unchanged in length, tone, and quality before vs. after.

---

## Phase A — Isolated backend logic (Tasks 1–7)

Everything in this phase is self-contained: new files plus one small, proven-safe relocation. Nothing here touches `chat.py`, `system_prompt.txt`, or any live request path. Each task is independently testable and safe to commit on its own.

### Task 1: Relocate `normalize_alias_key` into `backend/app/services/source_resolver.py`

**Why here, not left in `scripts/`:** `chat.py` runs on Railway with the backend service's root scoped to `backend/` — confirmed by `backend/railway.toml`'s `buildCommand = "pip install -r requirements.txt"` (relative, implying `backend/` is the working directory) and by grepping `backend/app/` for any import of `scripts.*` (zero hits). The backend cannot reach `scripts/source_resolver.py` today. `scripts/shared_ingest.py` already solves an identical problem for `embed_text` by importing it from `backend/app/services/embeddings.py` — this task applies that exact precedent to alias normalization.

**Files:**
- Create: `backend/app/services/source_resolver.py`
- Modify: `scripts/source_resolver.py` (Task 3, not this one — kept separate on purpose, see Task 3)

**Interfaces:**
- Produces: `normalize_alias_key(s: Optional[str]) -> str` — importable as `from app.services.source_resolver import normalize_alias_key`

- [ ] **Step 1: Create the new file with the relocated function, copied verbatim**

```python
# backend/app/services/source_resolver.py
"""
Canonical home for source-alias normalization, shared by the backend
(reference verification, this module) and scripts/source_resolver.py
(ingest-time attribution). Do not fork this function — scripts/source_resolver.py
imports it from here rather than defining its own copy (see Task 3).
"""
from __future__ import annotations

import re
from typing import Optional


def normalize_alias_key(s: Optional[str]) -> str:
    """Lowercase, trim, collapse internal whitespace to a single space.

    This is the sole normalization contract for source_aliases.alias_key.
    It must match the Python normalization used when migration 050 was seeded:
        re.sub(r'\\s+', ' ', s.lower().strip())
    """
    if not s:
        return ""
    return re.sub(r'\s+', ' ', s.lower().strip())
```

- [ ] **Step 2: Confirm the module imports cleanly**

Run: `cd /Users/alexwhitley/rhemata/backend && python3 -c "from app.services.source_resolver import normalize_alias_key; print(normalize_alias_key('  Derek   Prince '))"`
Expected: `derek prince`

- [ ] **Step 3: Commit**

```bash
cd /Users/alexwhitley/rhemata
git add backend/app/services/source_resolver.py
git commit -m "Add backend/app/services/source_resolver.py with relocated normalize_alias_key"
```

---

### Task 2: Prove the relocated function is byte-identical to the original, before anything depends on it

**Why this is its own task:** `normalize_alias_key` is load-bearing on the ingest side — every ingest script's attribution resolution depends on it matching migration 050's seeded normalization exactly. This task exists to make that provable, not assumed, before Task 3 repoints `scripts/source_resolver.py` at the new copy.

**Files:**
- Create: `scripts/test_source_resolver_relocation.py`

**Interfaces:**
- Consumes: `normalize_alias_key` from both `scripts/source_resolver.py` (old, still intact at this point) and `backend/app/services/source_resolver.py` (new, from Task 1)

- [ ] **Step 1: Write the comparison script**

```python
#!/usr/bin/env python3
"""
Proves backend/app/services/source_resolver.py's normalize_alias_key() is
byte-identical to the original scripts/source_resolver.py version, across
every live alias_key plus synthetic edge cases. Run BEFORE Task 3 repoints
scripts/source_resolver.py at the relocated function — this is the evidence
that repointing is safe, not an assumption.

Run from project root: python3 scripts/test_source_resolver_relocation.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

from supabase import create_client

from source_resolver import normalize_alias_key as old_normalize
from app.services.source_resolver import normalize_alias_key as new_normalize

SB_URL = os.environ["SUPABASE_URL"]
SB_SVC = os.environ["SUPABASE_SERVICE_KEY"]

EDGE_CASES = [
    None,
    "",
    "   ",
    "Derek Prince",
    "  Derek   Prince  ",
    "DEREK PRINCE",
    "John\tBevere",
    "John\n\nBevere",
    "1 Corinthians",
    "F.F. Bosworth",
    "An Unknown Christian",
]


def main():
    db = create_client(SB_URL, SB_SVC)

    mismatches = []

    print("Checking synthetic edge cases...")
    for s in EDGE_CASES:
        old_result = old_normalize(s)
        new_result = new_normalize(s)
        status = "OK" if old_result == new_result else "MISMATCH"
        print(f"  {status}  {s!r:30} -> old={old_result!r} new={new_result!r}")
        if old_result != new_result:
            mismatches.append((s, old_result, new_result))

    print("\nChecking every live alias_key...")
    result = db.table("source_aliases").select("alias_key").execute()
    rows = result.data or []
    for row in rows:
        key = row["alias_key"]
        old_result = old_normalize(key)
        new_result = new_normalize(key)
        if old_result != new_result:
            mismatches.append((key, old_result, new_result))

    print(f"Checked {len(rows)} live alias_key rows + {len(EDGE_CASES)} edge cases.")

    if mismatches:
        print(f"\nFAILED — {len(mismatches)} mismatch(es):")
        for s, old_result, new_result in mismatches:
            print(f"  input={s!r} old={old_result!r} new={new_result!r}")
        sys.exit(1)

    print("\nPASSED — relocated normalize_alias_key is byte-identical to the original "
          "on every live alias_key and every synthetic edge case.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

Run: `cd /Users/alexwhitley/rhemata && python3 scripts/test_source_resolver_relocation.py`
Expected: `PASSED — relocated normalize_alias_key is byte-identical to the original on every live alias_key and every synthetic edge case.`

If it fails, stop — do not proceed to Task 3 until every mismatch is resolved.

- [ ] **Step 3: Commit**

```bash
cd /Users/alexwhitley/rhemata
git add scripts/test_source_resolver_relocation.py
git commit -m "Add byte-identical proof for relocated normalize_alias_key"
```

---

### Task 3: Point `scripts/source_resolver.py` at the relocated function

**Files:**
- Modify: `scripts/source_resolver.py:1-36` (the module docstring and the `normalize_alias_key` definition)

**Interfaces:**
- Consumes: `app.services.source_resolver.normalize_alias_key` (from Task 1)
- Produces: `scripts.source_resolver.normalize_alias_key` (re-exported, same name, same behavior — every existing caller in `scripts/` is unaffected)

- [ ] **Step 1: Replace the local definition with an import**

Replace lines 1–36 of `scripts/source_resolver.py` (the module docstring through the end of the `normalize_alias_key` function body) with:

```python
#!/usr/bin/env python3
"""
Source resolver for Rhemata ingest pipeline.

normalize_alias_key() now lives in backend/app/services/source_resolver.py —
the canonical home, shared with the backend's reference-verification code
(see docs/superpowers/plans/2026-07-14-sp1-reference-pointer-backend.md).
Byte-identical relocation proven by scripts/test_source_resolver_relocation.py
before this repoint landed. Do not redefine normalize_alias_key here again —
import it, as below.

Usage from an ingest script:
    from source_resolver import resolve_source_id, SENTINEL_SOURCE_ID
    source_id, norm_key, via = resolve_source_id(db, source_name, author)
"""
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.services.source_resolver import normalize_alias_key

# Protected sentinel — documents with unresolved attribution land here via the
# documents.source_id column DEFAULT.  NEVER pass this UUID to a DELETE.
SENTINEL_SOURCE_ID = "267a09ac-76f3-43fb-901f-3015aef88e22"

# New Wine Magazine has a fixed source_id.  Use this constant in the live write
# path rather than a DB lookup — the alias is also seeded, but this avoids a
# round-trip for a value that never changes.
NEW_WINE_MAGAZINE_SOURCE_ID = "72b2f583-d7f9-4361-be1c-6d5aebe59fac"
```

Leave everything from `def resolve_source_id(...)` onward (currently starting at the old line 39) completely unchanged.

- [ ] **Step 2: Smoke-test that ingest scripts still import and resolve correctly**

Run: `cd /Users/alexwhitley/rhemata && python3 -c "
from scripts.source_resolver import normalize_alias_key, resolve_source_id, SENTINEL_SOURCE_ID
print(normalize_alias_key('  Derek   Prince '))
print(SENTINEL_SOURCE_ID)
"`

(If `scripts` is not a package importable this way in your shell, run instead from inside `scripts/`: `cd /Users/alexwhitley/rhemata/scripts && python3 -c "from source_resolver import normalize_alias_key, SENTINEL_SOURCE_ID; print(normalize_alias_key('  Derek   Prince ')); print(SENTINEL_SOURCE_ID)"`)

Expected: `derek prince` then the sentinel UUID, no import errors.

- [ ] **Step 3: Re-run the byte-identical proof script once more post-repoint, as a final check**

Run: `cd /Users/alexwhitley/rhemata && python3 scripts/test_source_resolver_relocation.py`
Expected: still PASSED (it now compares the same underlying function to itself via two import paths, which is fine — it's re-confirming the import wiring didn't break anything).

- [ ] **Step 4: Commit — this closes Phase A's prerequisite sub-phase on its own, separate from any SP1 feature code**

```bash
cd /Users/alexwhitley/rhemata
git add scripts/source_resolver.py
git commit -m "Point scripts/source_resolver.py at the relocated normalize_alias_key"
```

---

### Task 4: Add `is_source_servable()` — the exact license/visibility gate, callable directly

**Files:**
- Modify: `backend/app/services/source_resolver.py` (append to the file from Task 1)
- Create: `scripts/test_is_source_servable.py`

**Interfaces:**
- Consumes: a live Supabase client (same `get_supabase()` pattern used throughout `backend/app`)
- Produces: `is_source_servable(db, source_id: str) -> bool` — importable as `from app.services.source_resolver import is_source_servable`

- [ ] **Step 1: Append the function**

Add to the end of `backend/app/services/source_resolver.py`:

```python
def is_source_servable(db, source_id: str) -> bool:
    """Return True if this source may currently be served, using the exact
    same predicate as migration 049/056's SQL gate:

        s.license_status IN ('public_domain', 'owned')
        OR (NOT safe_mode_on AND s.visibility = 'shown')

    safe_mode is read fresh on every call — it is a global kill switch and
    must never be cached across requests.
    """
    safe_mode_result = (
        db.table("app_settings").select("value").eq("key", "safe_mode").limit(1).execute()
    )
    safe_mode_on = bool(safe_mode_result.data) and safe_mode_result.data[0]["value"] == "on"

    source_result = (
        db.table("sources").select("license_status, visibility").eq("id", source_id).limit(1).execute()
    )
    if not source_result.data:
        return False

    row = source_result.data[0]
    if row["license_status"] in ("public_domain", "owned"):
        return True
    return (not safe_mode_on) and row["visibility"] == "shown"
```

- [ ] **Step 2: Write a live test proving it against one known-servable and one known-not-servable real source**

`F.F. Bosworth` is confirmed `unlicensed`/`hidden` in CLAUDE.md's decision log (migration 050 entry) — a real, aliased, currently-not-servable source. Confirm this and find one confirmed-servable source (any `public_domain` or `owned` row) live before writing assertions.

```python
#!/usr/bin/env python3
"""
Proves is_source_servable() against two real, known-state sources:
one confirmed servable, one confirmed not servable (F.F. Bosworth —
unlicensed/hidden per CLAUDE.md's migration-050 decision entry).

Run from project root: python3 scripts/test_is_source_servable.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

from supabase import create_client
from app.services.source_resolver import is_source_servable, normalize_alias_key

SB_URL = os.environ["SUPABASE_URL"]
SB_SVC = os.environ["SUPABASE_SERVICE_KEY"]


def main():
    db = create_client(SB_URL, SB_SVC)

    # Known NOT servable: F.F. Bosworth (unlicensed/hidden).
    bosworth_alias = db.table("source_aliases").select("source_id").eq(
        "alias_key", normalize_alias_key("F.F. Bosworth")
    ).limit(1).execute()
    assert bosworth_alias.data, "Expected an alias row for 'F.F. Bosworth' — none found, check the alias_key spelling live"
    bosworth_id = bosworth_alias.data[0]["source_id"]
    bosworth_row = db.table("sources").select("license_status, visibility, name").eq("id", bosworth_id).limit(1).execute()
    print(f"F.F. Bosworth source row: {bosworth_row.data}")
    assert is_source_servable(db, bosworth_id) is False, "F.F. Bosworth should NOT be servable (unlicensed/hidden)"
    print("PASS — F.F. Bosworth correctly not servable")

    # Known servable: pick the first public_domain source live.
    pd_source = db.table("sources").select("id, name").eq("license_status", "public_domain").limit(1).execute()
    assert pd_source.data, "Expected at least one public_domain source live"
    pd_id = pd_source.data[0]["id"]
    print(f"Testing known-servable public_domain source: {pd_source.data[0]['name']}")
    assert is_source_servable(db, pd_id) is True, f"{pd_source.data[0]['name']} (public_domain) should be servable"
    print("PASS — public_domain source correctly servable")

    # Unknown source_id — should fail closed, not throw.
    assert is_source_servable(db, "00000000-0000-0000-0000-000000000000") is False
    print("PASS — nonexistent source_id correctly fails closed")

    print("\nALL PASSED")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run it**

Run: `cd /Users/alexwhitley/rhemata && python3 scripts/test_is_source_servable.py`
Expected: `ALL PASSED`

- [ ] **Step 4: Commit**

```bash
cd /Users/alexwhitley/rhemata
git add backend/app/services/source_resolver.py scripts/test_is_source_servable.py
git commit -m "Add is_source_servable() reusing the exact license/visibility gate predicate"
```

---

### Task 5: Biblical-figures reject list — the independent backstop guard

**Files:**
- Create: `backend/app/services/biblical_figures.py`
- Create: `scripts/test_biblical_figures.py`

**Interfaces:**
- Consumes: `normalize_alias_key` (Task 1)
- Produces: `is_biblical_figure(name: str) -> bool` — importable as `from app.services.biblical_figures import is_biblical_figure`

- [ ] **Step 1: Create the module**

```python
# backend/app/services/biblical_figures.py
"""
A fixed, manually curated reject list of biblical-figure names. A name on
this list can NEVER resolve as a teacher pointer, independent of whether it
also happens to match a real, servable source in source_aliases — this is a
deliberate second guard (see docs/superpowers/plans/2026-07-14-sp1-reference-pointer-backend.md),
not a substitute for the license/visibility gate.

Matching is EXACT on the normalized string, not substring — "paul" is
rejected, but "paul washer" (a distinct full name) is not, so a real corpus
teacher whose full name happens to start with a biblical first name is
unaffected.

This list is intentionally bounded to major, commonly-referenced figures.
Known limitation: it will not catch every obscure biblical name. Extend it
if a future test case or real usage surfaces a gap — do not treat this as
exhaustive.
"""
from __future__ import annotations

from app.services.source_resolver import normalize_alias_key

_BIBLICAL_FIGURE_NAMES = [
    # Patriarchs / OT narrative
    "adam", "eve", "noah", "abraham", "sarah", "isaac", "rebekah", "jacob",
    "rachel", "leah", "joseph", "moses", "aaron", "miriam", "joshua", "caleb",
    "deborah", "gideon", "samson", "ruth", "naomi", "samuel", "saul", "david",
    "bathsheba", "solomon", "elijah", "elisha", "job", "esther", "mordecai",
    "nehemiah", "ezra",
    # OT prophets
    "isaiah", "jeremiah", "ezekiel", "daniel", "hosea", "joel", "amos",
    "obadiah", "jonah", "micah", "nahum", "habakkuk", "zephaniah", "haggai",
    "zechariah", "malachi",
    # NT — gospels and epistles
    "mary", "elizabeth", "john the baptist", "jesus", "peter", "andrew",
    "james", "john", "philip", "bartholomew", "thomas", "matthew",
    "thaddaeus", "simon", "judas", "paul", "barnabas", "silas", "timothy",
    "titus", "luke", "mark", "stephen", "cornelius", "lydia", "priscilla",
    "aquila", "apollos", "lazarus", "martha", "nicodemus", "zacchaeus",
    "mary magdalene",
]

BIBLICAL_FIGURE_KEYS = frozenset(normalize_alias_key(n) for n in _BIBLICAL_FIGURE_NAMES)


def is_biblical_figure(name: str) -> bool:
    """Exact-match (post-normalization) check against the reject list."""
    return normalize_alias_key(name) in BIBLICAL_FIGURE_KEYS
```

- [ ] **Step 2: Write unit tests proving exact-match behavior**

```python
#!/usr/bin/env python3
"""
Unit tests for is_biblical_figure() — no DB required.

Run from project root: python3 scripts/test_biblical_figures.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services.biblical_figures import is_biblical_figure

CASES = [
    ("Paul", True),
    ("paul", True),
    ("  PAUL  ", True),
    ("Paul Washer", False),   # distinct full name — must NOT be caught
    ("Moses", True),
    ("John", True),
    ("John Bevere", False),   # distinct full name — must NOT be caught
    ("Derek Prince", False),
    ("Peter", True),
    ("Peter Parker", False),
    ("", False),
    (None, False),
]


def main():
    failures = []
    for name, expected in CASES:
        actual = is_biblical_figure(name)
        status = "OK" if actual == expected else "FAIL"
        print(f"  {status}  is_biblical_figure({name!r}) = {actual} (expected {expected})")
        if actual != expected:
            failures.append((name, expected, actual))

    if failures:
        print(f"\nFAILED — {len(failures)} case(s) wrong")
        sys.exit(1)
    print("\nALL PASSED")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run it**

Run: `cd /Users/alexwhitley/rhemata && python3 scripts/test_biblical_figures.py`
Expected: `ALL PASSED`

- [ ] **Step 4: Commit**

```bash
cd /Users/alexwhitley/rhemata
git add backend/app/services/biblical_figures.py scripts/test_biblical_figures.py
git commit -m "Add biblical-figures reject list as an independent teacher-resolution backstop"
```

---

### Task 6: Build `reference_verifier.py` — proposal parsing, presence check, verse and teacher resolution

**Files:**
- Create: `backend/app/services/reference_verifier.py`

**Interfaces:**
- Consumes: `normalize_alias_key`, `is_source_servable` (Task 1, Task 4); `is_biblical_figure` (Task 5); `BOOK_MAP` from `app.constants` (existing, unmodified — the same dict `app.routers.study.parse_ref` uses for book-name matching; this task writes its own range-aware parser against that dict rather than importing `parse_ref` directly, since `parse_ref` has no range support to reuse)
- Produces:
  - `parse_reference_mentions(raw_output: str) -> List[Dict]` — each dict `{"type": "verse"|"teacher", "raw": str}`
  - `verify_references(answer_text: str, raw_output: str, db) -> List[Dict]` — the top-level entry point `chat.py` calls

- [ ] **Step 1: Write the module**

```python
# backend/app/services/reference_verifier.py
"""
SP1 reference-pointer verifier. Takes what the writer PROPOSED (parsed from
the model's <reference_mentions> block) and what the model ACTUALLY WROTE
(the final <answer> text), and returns only the subset that survives every
independent guard below. Anything that fails any guard is dropped silently
— this module never raises past its own top-level try/except, and never
partially-credits a mention.

Guard order (all four required, in this order for efficiency — a mention
must survive all of them):
  1. Presence  — the proposed string must literally appear in answer_text.
     Also the SOLE source of occurrence positions (verses: every match;
     teachers: first match only) — the model's own claims are never
     trusted for position.
  2. Resolution — verses: parse_ref (single or range) + a real verses-table
     row for every endpoint. Teachers: alias-key lookup against
     source_aliases, must not be the sentinel/MISS, must pass the license/
     visibility gate (is_source_servable).
  3. Biblical-figure backstop — independent of #2's result. Runs regardless
     of what source_aliases says.

See docs/superpowers/plans/2026-07-14-sp1-reference-pointer-backend.md for
the full design rationale.
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple

from app.constants import BOOK_MAP
from app.services.biblical_figures import is_biblical_figure
from app.services.source_resolver import is_source_servable, normalize_alias_key

logger = logging.getLogger(__name__)

_MENTIONS_BLOCK_RE = re.compile(
    r"<reference_mentions>(.*?)</reference_mentions>", re.DOTALL
)
_MENTION_LINE_RE = re.compile(r"^(VERSE|TEACHER):\s*(.+)$")

_SENTINEL_SOURCE_ID = "267a09ac-76f3-43fb-901f-3015aef88e22"


def parse_reference_mentions(raw_output: str) -> List[Dict]:
    """Extract and parse the <reference_mentions> block from the model's
    full raw output. Malformed or missing lines are skipped individually —
    never fatal, never drops the whole block for one bad line.
    """
    block_match = _MENTIONS_BLOCK_RE.search(raw_output)
    if not block_match:
        return []

    proposals = []  # type: List[Dict]
    for line in block_match.group(1).splitlines():
        line = line.strip()
        if not line:
            continue
        m = _MENTION_LINE_RE.match(line)
        if not m:
            continue  # malformed line — skip silently, per-line fail-quiet
        kind, raw = m.group(1), m.group(2).strip()
        if not raw:
            continue
        proposals.append({"type": "verse" if kind == "VERSE" else "teacher", "raw": raw})
    return proposals


def find_occurrences(answer_text: str, raw: str) -> List[int]:
    """Literal, case-sensitive substring search. Returns every match start
    index, or [] if the string never appears — this IS the presence check.
    """
    if not raw:
        return []
    positions = []
    start = 0
    while True:
        idx = answer_text.find(raw, start)
        if idx == -1:
            break
        positions.append(idx)
        start = idx + 1
    return positions


def _parse_verse_or_range(ref: str) -> Optional[Tuple[str, int, int, Optional[int]]]:
    """Parse 'Romans 8:28' or 'Romans 8:26-28' / 'Romans 8:26–28' into
    (abbrev, chapter, verse_start, verse_end_or_None). Reuses the same
    book-name matching BOOK_MAP already uses in app.routers.study.parse_ref
    — this is an extension to support ranges, not a fork of book matching.
    Returns None if the book, chapter, or verse can't be parsed at all
    (e.g. a vague reference like "verse 26" or "that chapter" has no book
    match and always returns None here).
    """
    ref = ref.strip()
    m = re.match(r'^(\d?\s*[A-Za-z ]+?)\s+(\d+):(\d+)(?:[-–](\d+))?$', ref)
    if not m:
        return None

    book_raw = m.group(1).strip().lower()
    chapter = int(m.group(2))
    verse_start = int(m.group(3))
    verse_end = int(m.group(4)) if m.group(4) else None

    book_normalized = re.sub(r'^(\d)\s*', r'\1 ', book_raw).strip()
    abbrev = BOOK_MAP.get(book_normalized) or BOOK_MAP.get(book_normalized.rstrip('s'))
    if not abbrev:
        return None

    return abbrev, chapter, verse_start, verse_end


def _resolve_verse_row(db, abbrev: str, chapter: int, verse: int) -> bool:
    verse_id = f"{abbrev}.{chapter}.{verse}"
    result = db.table("verses").select("verse_id").eq("verse_id", verse_id).limit(1).execute()
    return bool(result.data)


def verify_verse_mention(db, raw: str) -> bool:
    """True only if the whole reference (single verse or full range)
    resolves to real rows. A range fails whole if either endpoint is bad —
    no partial credit.
    """
    parsed = _parse_verse_or_range(raw)
    if not parsed:
        return False
    abbrev, chapter, verse_start, verse_end = parsed

    if not _resolve_verse_row(db, abbrev, chapter, verse_start):
        return False
    if verse_end is not None:
        if not _resolve_verse_row(db, abbrev, chapter, verse_end):
            return False
    return True


def verify_teacher_mention(db, raw: str) -> Optional[str]:
    """Returns the resolved source_id if this name passes every teacher
    guard, else None. Biblical-figure check runs first and short-circuits
    — a hit here means the alias table is never even consulted.
    """
    if is_biblical_figure(raw):
        return None

    key = normalize_alias_key(raw)
    if not key:
        return None

    alias_result = (
        db.table("source_aliases").select("source_id").eq("alias_key", key).limit(1).execute()
    )
    if not alias_result.data:
        return None

    source_id = alias_result.data[0]["source_id"]
    if source_id == _SENTINEL_SOURCE_ID:
        return None

    if not is_source_servable(db, source_id):
        return None

    return source_id


def verify_references(answer_text: str, raw_output: str, db) -> List[Dict]:
    """Top-level entry point. Never raises — any unexpected failure
    anywhere in this function results in an empty list, never a broken
    request. Returns a list of verified references, each:
        {"type": "verse", "raw": str, "positions": [int, ...]}
        {"type": "teacher", "raw": str, "position": int, "source_id": str}
    """
    try:
        proposals = parse_reference_mentions(raw_output)
        verified = []  # type: List[Dict]

        for proposal in proposals:
            raw = proposal["raw"]
            positions = find_occurrences(answer_text, raw)
            if not positions:
                continue  # presence check failed — model reported something not actually there

            if proposal["type"] == "verse":
                if not verify_verse_mention(db, raw):
                    continue
                verified.append({"type": "verse", "raw": raw, "positions": positions})
            else:
                source_id = verify_teacher_mention(db, raw)
                if not source_id:
                    continue
                verified.append({
                    "type": "teacher",
                    "raw": raw,
                    "position": positions[0],
                    "source_id": source_id,
                })

        return verified
    except Exception:
        logger.exception("Reference verification failed — returning no pointers")
        return []
```

- [ ] **Step 2: Confirm the module imports cleanly**

Run: `cd /Users/alexwhitley/rhemata/backend && python3 -c "from app.services.reference_verifier import verify_references; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /Users/alexwhitley/rhemata
git add backend/app/services/reference_verifier.py
git commit -m "Add reference_verifier.py — presence, resolution, and biblical-figure guards"
```

---

### Task 7: Track-B tests — constructed/injected verifier cases

These are deterministic checks against `reference_verifier.py` directly, run regardless of whether a live generation happens to produce the same failure shape. Two of these (a biblical-figure misclassification, a plausible-but-wrong verse number) are genuinely unlikely to come up on demand in a live run — fine reasons to construct them directly. **The third is different, and worth stating precisely:** a real, currently-hidden-or-unlicensed teacher (F.F. Bosworth, B3) is NOT tested here because it "can't happen organically." It can — Claude carries its own general knowledge of thousands of real teachers and can name one directly, including one this library has deliberately hidden or never licensed, even when retrieval surfaces zero content about them. This case is constructed anyway because the servability check is the single guard standing between the panel and pointing users at content the product isn't licensed to serve, and a guard that safety-critical needs to be proven on demand, every time — not left dependent on whether a given live run happens to mention that one name. Treat it as load-bearing on every teacher mention, not a corner case.

**Files:**
- Create: `scripts/test_reference_verifier.py`

**Interfaces:**
- Consumes: `verify_references`, `parse_reference_mentions`, `find_occurrences` (Task 6)

- [ ] **Step 1: Write the test script**

```python
#!/usr/bin/env python3
"""
Track-B (constructed/injected) tests for the SP1 reference verifier.
Covers: biblical-figure backstop, nonexistent verse, not-servable teacher
(F.F. Bosworth), MISS/sentinel teacher, presence-check drop, occurrence
anchoring (verse=every occurrence, teacher=first only), and malformed/
vague-reference robustness.

Run from project root: python3 scripts/test_reference_verifier.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

from supabase import create_client
from app.services.reference_verifier import (
    parse_reference_mentions,
    find_occurrences,
    verify_references,
)
from app.services.source_resolver import normalize_alias_key

SB_URL = os.environ["SUPABASE_URL"]
SB_SVC = os.environ["SUPABASE_SERVICE_KEY"]

db = create_client(SB_URL, SB_SVC)
failures = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"  {status}  {label}")
    if not condition:
        failures.append(label)


def main():
    # --- Parsing robustness ---
    raw_output_malformed = "<answer>...</answer>\n<reference_mentions>\nVERSE: Romans 8:28\nGARBAGE LINE\nTEACHER:\n</reference_mentions>"
    proposals = parse_reference_mentions(raw_output_malformed)
    check(
        "Malformed lines are skipped, well-formed line survives",
        proposals == [{"type": "verse", "raw": "Romans 8:28"}],
    )

    check(
        "Missing <reference_mentions> block returns empty, not an error",
        parse_reference_mentions("<answer>no block here</answer>") == [],
    )

    # --- B1: Biblical-figure backstop ---
    answer_text_1 = "Paul's letter to the Romans is foundational."
    raw_output_1 = "<reference_mentions>\nTEACHER: Paul\n</reference_mentions>"
    result_1 = verify_references(answer_text_1, raw_output_1, db)
    check("B1: 'Paul' proposed as teacher never resolves", result_1 == [])

    # --- B2: Nonexistent verse (Genesis 50 has 26 verses) ---
    answer_text_2 = "This is discussed in Genesis 50:99."
    raw_output_2 = "<reference_mentions>\nVERSE: Genesis 50:99\n</reference_mentions>"
    result_2 = verify_references(answer_text_2, raw_output_2, db)
    check("B2: nonexistent verse (Genesis 50:99) never resolves", result_2 == [])

    # --- B3: Not-servable teacher (F.F. Bosworth — unlicensed/hidden) ---
    bosworth_alias = db.table("source_aliases").select("source_id").eq(
        "alias_key", normalize_alias_key("F.F. Bosworth")
    ).limit(1).execute()
    if not bosworth_alias.data:
        print("  SKIP  B3: no live alias for 'F.F. Bosworth' — confirm live data before treating this as a gap")
    else:
        answer_text_3 = "F.F. Bosworth taught extensively on divine healing."
        raw_output_3 = "<reference_mentions>\nTEACHER: F.F. Bosworth\n</reference_mentions>"
        result_3 = verify_references(answer_text_3, raw_output_3, db)
        check("B3: F.F. Bosworth (real alias, not servable) never resolves", result_3 == [])

    # --- MISS / sentinel: a name with no alias at all ---
    answer_text_4 = "Some Nonexistent Teacher Name talks about grace."
    raw_output_4 = "<reference_mentions>\nTEACHER: Some Nonexistent Teacher Name\n</reference_mentions>"
    result_4 = verify_references(answer_text_4, raw_output_4, db)
    check("MISS: unaliased name never resolves (and never sentinel-resolves)", result_4 == [])

    # --- Presence-check drop: proposal not actually in the text ---
    answer_text_5 = "This answer never mentions any verse at all."
    raw_output_5 = "<reference_mentions>\nVERSE: Romans 8:28\n</reference_mentions>"
    result_5 = verify_references(answer_text_5, raw_output_5, db)
    check("Presence check drops a proposal that never appears in the answer", result_5 == [])

    # --- Vague reference: no book match, always fails ---
    answer_text_6 = "That verse we discussed earlier is important."
    raw_output_6 = "<reference_mentions>\nVERSE: that verse\nVERSE: verse 26\n</reference_mentions>"
    result_6 = verify_references(answer_text_6, raw_output_6, db)
    check("Vague references ('that verse', 'verse 26') never resolve", result_6 == [])

    # --- Occurrence anchoring: verse repeated 2x, both anchored ---
    answer_text_7 = "Romans 8:28 tells us this. Later, Romans 8:28 is echoed again."
    raw_output_7 = "<reference_mentions>\nVERSE: Romans 8:28\n</reference_mentions>"
    result_7 = verify_references(answer_text_7, raw_output_7, db)
    check(
        "Repeated verse mention anchors every occurrence",
        len(result_7) == 1 and result_7[0]["type"] == "verse" and len(result_7[0]["positions"]) == 2,
    )

    print(f"\n{'ALL PASSED' if not failures else f'{len(failures)} FAILURE(S): ' + ', '.join(failures)}")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

Run: `cd /Users/alexwhitley/rhemata && python3 scripts/test_reference_verifier.py`
Expected: `ALL PASSED` (or an explicit `SKIP` line for B3 if the live alias data has changed — investigate before proceeding if so, do not silently ignore).

- [ ] **Step 3: Commit**

```bash
cd /Users/alexwhitley/rhemata
git add scripts/test_reference_verifier.py
git commit -m "Add Track-B constructed tests for the SP1 reference verifier"
```

---

## MID-POINT STOP

Everything up to here is committed, isolated, and independently proven: the alias-normalization relocation (with byte-identical proof), the servability check, the biblical-figures backstop, and the full verifier module with six passing constructed test cases. **Nothing in the live `/chat` path has been touched.** This is a safe point to pause — review the four commits so far before continuing into Phase B, which touches `system_prompt.txt` and the live streaming code in `chat.py`.

---

## Phase B — Wire into the live answer path, then prove it on real answers (Tasks 8–15)

### Task 8: Build the shared real-answer generation helper

**Why this is its own task:** two later tasks (the answer-quality baseline/regression check, and the Track-A pinned reference test) both need to run a real question through the actual retrieval + Claude answer-writing path outside the live `/chat` endpoint. Rather than inline that ~40 lines of retrieval-and-call logic twice, it lives in exactly one place, imported by both.

**Files:**
- Create: `scripts/sp1_answer_harness.py`

**Interfaces:**
- Consumes: `hybrid_search_rrf`, `_is_citable`, `ANSWER_SYSTEM_BLOCKS`, `_get_anthropic` (all existing, unmodified, from `app.routers.chat`)
- Produces: `generate_real_answer(question: str, db) -> Tuple[str, str]` — returns `(answer_text, raw_output)`

- [ ] **Step 1: Write the helper**

```python
# scripts/sp1_answer_harness.py
"""
Shared real-answer generation helper for SP1 test scripts. Runs a question
through the actual retrieval + Claude answer-writing path (same system
prompt, same model, same retrieval fusion as production) via direct
function calls — NOT the live /chat HTTP endpoint, so no weekly-query-limit
/ guest-limit metering and no conversations/messages rows are touched (per
Alex's confirmed harness choice). Used by the answer-quality baseline/
regression scripts (Tasks 9, 12) and the Track-A pinned reference test
(Task 13) — the retrieval+Claude-call logic lives in exactly one place.

Note: ANSWER_SYSTEM_BLOCKS is read from system_prompt.txt once, at import
time, inside app.routers.chat. Each script that imports this helper does so
in its own fresh `python3` process, so a script run before Task 10's
system_prompt.txt edit picks up the OLD prompt, and one run after picks up
the NEW prompt — no special handling needed, just run things in the order
the tasks specify.
"""
import sys
from pathlib import Path
from typing import Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.routers.chat import hybrid_search_rrf, _is_citable, ANSWER_SYSTEM_BLOCKS, _get_anthropic


def generate_real_answer(question: str, db) -> Tuple[str, str]:
    """Returns (answer_text, raw_output). answer_text is what a user would
    see (the <answer> block's contents); raw_output is the model's complete
    raw response, including anything written after </answer>.
    """
    scores, _ = hybrid_search_rrf(question, db, include_copyrighted=True)
    ranked = sorted(scores.items(), key=lambda x: x[1][0], reverse=True)
    chunks = [chunk for _, (_, chunk) in ranked[:8]]

    context_parts = []
    source_num = 0
    for c in chunks:
        if _is_citable(c):
            source_num += 1
            label = f"[Source {source_num}]"
        else:
            label = "[Background]"
        context_parts.append(
            f"{label} (source_kind={c.get('source_kind') or c.get('source_type', 'unknown')}, "
            f"citation_mode={c.get('citation_mode', 'citable')}) "
            f"\"{c.get('title', 'Unknown')}\" by {c.get('author', 'Unknown')}\n{c['content']}"
        )
    context = "\n\n---\n\n".join(context_parts)

    history = [{
        "role": "user",
        "content": f"Sources:\n{context}\n\nQuestion: {question}",
    }]

    client = _get_anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1500,
        system=ANSWER_SYSTEM_BLOCKS,
        messages=history,
        stream=False,
    )
    raw_output = response.content[0].text

    answer_start = raw_output.find("<answer>")
    answer_end = raw_output.find("</answer>")
    if answer_start != -1 and answer_end != -1:
        answer = raw_output[answer_start + len("<answer>"):answer_end].strip()
    else:
        answer = raw_output.strip()

    return answer, raw_output
```

- [ ] **Step 2: Smoke-test it**

Run: `cd /Users/alexwhitley/rhemata && python3 -c "
import sys; sys.path.insert(0, 'scripts')
from dotenv import load_dotenv
load_dotenv('backend/app/.env')
import os
from supabase import create_client
from sp1_answer_harness import generate_real_answer
db = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_KEY'])
answer, raw = generate_real_answer('What does it mean to be baptized in the Holy Spirit?', db)
print(len(answer), 'chars')
print(answer[:200])
"`
Expected: a real answer prints, no exceptions, non-trivial length (well over 200 chars for this question).

- [ ] **Step 3: Commit**

```bash
cd /Users/alexwhitley/rhemata
git add scripts/sp1_answer_harness.py
git commit -m "Add shared real-answer generation helper for SP1 test scripts"
```

---

### Task 9: Capture answer-quality baseline — BEFORE the prompt change lands

**Why this must run before Task 10:** the system-prompt change is the one part of this feature that is not purely additive — it touches the instructions behind every single answer, not just SP1's new block. The reference-resolution test set proves pointers resolve correctly; nothing so far proves the answers themselves still read the same. This task captures the "before" side of that comparison. Do not skip this and do not run it after Task 10 — there would be nothing left to compare against.

**Files:**
- Create: `scripts/test_sp1_answer_quality_baseline.py`
- Creates at runtime: `scripts/sp1_answer_quality_baseline.json` (the saved baseline, read back by Task 12)

**Interfaces:**
- Consumes: `generate_real_answer` (Task 8)

- [ ] **Step 1: Write the capture script**

```python
#!/usr/bin/env python3
"""
SP1 answer-quality baseline capture. Run this BEFORE Task 10's
system_prompt.txt edit lands. Saves real answers to a fixed set of
ordinary questions using the CURRENT (pre-SP1) prompt, for later
side-by-side comparison in Task 12. This is an explicit Phase B
acceptance criterion, not optional: the writer-instruction change touches
every answer, so proving ordinary answers are unchanged matters as much as
proving references resolve correctly.

Run from project root: python3 scripts/test_sp1_answer_quality_baseline.py
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

from supabase import create_client
from sp1_answer_harness import generate_real_answer

SB_URL = os.environ["SUPABASE_URL"]
SB_SVC = os.environ["SUPABASE_SERVICE_KEY"]

BASELINE_FILE = Path(__file__).resolve().parent / "sp1_answer_quality_baseline.json"

# A fixed set of ordinary questions, deliberately unrelated to any SP1 hard
# case — this checks general answer quality (length, tone, structure), not
# reference resolution.
QUESTIONS = [
    "What does it mean to be baptized in the Holy Spirit?",
    "How should a believer respond when a prayer for healing isn't answered?",
    "What is the charismatic understanding of prophetic ministry today?",
    "Why do Spirit-filled Christians believe tongues is still active?",
    "What does it look like to walk in the fruit of the Spirit day to day?",
]


def main():
    db = create_client(SB_URL, SB_SVC)
    baseline = {}
    for question in QUESTIONS:
        answer, _ = generate_real_answer(question, db)
        baseline[question] = answer
        print(f"Captured baseline for: {question!r} ({len(answer)} chars)")

    BASELINE_FILE.write_text(json.dumps(baseline, indent=2))
    print(f"\nSaved {len(baseline)} baseline answers to {BASELINE_FILE}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

Run: `cd /Users/alexwhitley/rhemata && python3 scripts/test_sp1_answer_quality_baseline.py`
Expected: five "Captured baseline for..." lines, then a confirmation that `sp1_answer_quality_baseline.json` was saved.

- [ ] **Step 3: Commit — the script only; the generated baseline JSON is working data, not something to hand-review yet**

```bash
cd /Users/alexwhitley/rhemata
git add scripts/test_sp1_answer_quality_baseline.py
git commit -m "Add SP1 answer-quality baseline capture script (pre-prompt-change)"
```

---

### Task 10: Add the `<reference_mentions>` instructions to `system_prompt.txt`

**Files:**
- Modify: `backend/app/system_prompt.txt` (insert after the existing "Response Structure" section, which currently ends after the `<answer>...</answer>` block description, before "# Rules for the `<answer>` block")

- [ ] **Step 1: Insert the new section**

Find this exact text in `backend/app/system_prompt.txt` (currently lines 34–60, the "Response Structure" section ending with the `<answer>` tag description):

```
<answer>
Write your final, verified answer here. This is the only part the user sees.
</answer>

# Rules for the <answer> block
```

Replace it with:

```
<answer>
Write your final, verified answer here. This is the only part the user sees.
</answer>

If the user's question names a specific Bible verse or passage (e.g. "What
does Romans 8:28 mean?" or "explain John 3:16"), your answer above must
explicitly name that same reference back in its text — not just discuss
the passage thematically without ever writing out the reference. If you
never name it, there is nothing for the system to confirm or point back to.

<reference_mentions>
After closing </answer>, list every verse reference and named-teacher
mention you used inside <answer>, one per line, in the order it appears.
This block is never shown to the user — it exists only so the system can
confirm which mentions are safe to turn into study-panel links.

Format, one line per mention:
- A Bible verse or verse range you named: `VERSE: <exact text as written in the answer>`
  Example: `VERSE: Romans 8:28` or `VERSE: Romans 8:26-28`.
  List every verse you named, including repeats — do not deduplicate.
- A named teacher from the library, but ONLY the FIRST time you used their
  FULL NAME in this answer: `TEACHER: <exact full name as written>`
  Example: `TEACHER: Derek Prince`.
  Do NOT list a teacher's later, short-form mentions (e.g. "Prince" after
  "Derek Prince" earlier in the same answer) — only the first full-name
  occurrence, once.
- NEVER list a biblical figure (Paul, Moses, Peter, Moses, David, etc.) as
  a TEACHER line, even if you named them in <answer> — they are historical
  and biblical figures, not teachers in this library.
- If you made no verse or teacher mentions in <answer>, leave this block
  empty.
</reference_mentions>

# Rules for the <answer> block
```

- [ ] **Step 2: Confirm the file still loads without error**

Run: `cd /Users/alexwhitley/rhemata/backend && python3 -c "
from pathlib import Path
text = (Path('app') / 'system_prompt.txt').read_text()
assert '<reference_mentions>' in text
assert 'Rules for the <answer> block' in text
print('OK, length:', len(text))
"`
Expected: `OK, length: <some number>` with no exception.

- [ ] **Step 3: Commit**

```bash
cd /Users/alexwhitley/rhemata
git add backend/app/system_prompt.txt
git commit -m "system_prompt: add <reference_mentions> instructions + user-verse-naming rule for SP1"
```

---

### Task 11: Wire the verifier into `chat.py`'s streaming loop

**Why the stream-parser guard matters:** `chat.py`'s current tag-boundary parser (lines 916–955 in the version read for this plan) toggles `in_answer` purely by watching for `<answer>` / `</answer>` substrings in the buffer, with no "already closed, never reopen" flag. Today that's harmless because nothing meaningful is ever written after `</answer>`. Task 10 changes that — the model now writes a real block after `</answer>`. If that trailing content ever happened to contain the literal substring `<answer>` again (an echo, a stray quote, anything), the existing parser would technically reopen and leak it to the user as if it were more answer text. This task adds the guard as a required companion to the wiring, not an optional hardening.

**Files:**
- Modify: `backend/app/routers/chat.py:883-999` (the `generate()` function's streaming section, tag-parsing loop, and final meta assembly)

**Interfaces:**
- Consumes: `verify_references` from `app.services.reference_verifier` (Task 6)
- Produces: a new `verified_references` key in the final SSE `meta` event

- [ ] **Step 1: Add the "already closed" guard flag alongside the existing state**

Find (currently `chat.py:884-887`):

```python
        # Stream from Anthropic Claude, extracting only <answer> content (Change 4: singleton)
        raw_full = []
        answer_parts = []
        in_answer = False
        buffer = ""
```

Replace with:

```python
        # Stream from Anthropic Claude, extracting only <answer> content (Change 4: singleton)
        raw_full = []
        answer_parts = []
        in_answer = False
        answer_closed = False  # SP1: once True, never re-enter in_answer — protects
                                # against a stray "<answer>" substring appearing in
                                # content written after </answer> (see Task 11 note above).
        buffer = ""
```

- [ ] **Step 2: Guard the tag-open check so it never fires again after the answer has closed once**

Find (currently `chat.py:916-917`):

```python
                if not in_answer:
                    # Check if <answer> tag has appeared in the buffer
```

Replace with:

```python
                if not in_answer and not answer_closed:
                    # Check if <answer> tag has appeared in the buffer
```

- [ ] **Step 3: Set the guard when the closing tag is found**

Find (currently `chat.py:938-946`, inside the `else:  # Inside <answer>` branch):

```python
                else:
                    # Inside <answer> — check for closing tag
                    close_pos = buffer.find("</answer>")
                    if close_pos != -1:
                        part = buffer[:close_pos]
                        if part:
                            answer_parts.append(part)
                            yield _sse(json.dumps({"token": part}))
                        in_answer = False
                        buffer = ""
```

Replace with:

```python
                else:
                    # Inside <answer> — check for closing tag
                    close_pos = buffer.find("</answer>")
                    if close_pos != -1:
                        part = buffer[:close_pos]
                        if part:
                            answer_parts.append(part)
                            yield _sse(json.dumps({"token": part}))
                        in_answer = False
                        answer_closed = True  # SP1 guard — see note above
                        buffer = ""
```

- [ ] **Step 4: After the streaming loop, compute the raw output and run the verifier**

Find (currently `chat.py:968-975`):

```python
        # If we never found <answer> tags, the full raw output is the answer
        if not answer_parts:
            raw_text = "".join(raw_full).strip()
            answer_parts.append(raw_text)
            yield _sse(json.dumps({"token": raw_text}))

        answer = "".join(answer_parts).strip()
```

Replace with:

```python
        # If we never found <answer> tags, the full raw output is the answer
        if not answer_parts:
            raw_text = "".join(raw_full).strip()
            answer_parts.append(raw_text)
            yield _sse(json.dumps({"token": raw_text}))

        answer = "".join(answer_parts).strip()
        raw_output = "".join(raw_full)

        # SP1: verify proposed verse/teacher mentions against real data.
        # Wrapped so any failure here can never affect the answer already
        # sent, the conversation save below, or the final meta event.
        try:
            from app.services.reference_verifier import verify_references
            verified_references = verify_references(answer, raw_output, db)
        except Exception:
            logger.exception("SP1 reference verification failed — continuing without pointers")
            verified_references = []
```

- [ ] **Step 5: Attach the result to the final meta event**

Find (currently `chat.py:992-993`):

```python
        # Send metadata and close
        meta = {"citations": citations, "conversation_id": conversation_id, "message_id": message_id}
```

Replace with:

```python
        # Send metadata and close
        meta = {
            "citations": citations,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "verified_references": verified_references,
        }
```

- [ ] **Step 6: Confirm the module still imports and the app still starts**

Run: `cd /Users/alexwhitley/rhemata/backend && python3 -c "from app.routers import chat; print('OK')"`
Expected: `OK`, no import errors.

- [ ] **Step 7: Commit**

```bash
cd /Users/alexwhitley/rhemata
git add backend/app/routers/chat.py
git commit -m "chat.py: wire SP1 reference verifier into the answer stream, additive meta field"
```

---

### Task 12: Answer-quality regression check — run AFTER the prompt change and chat.py wiring

**Why this is a required acceptance criterion, not an optional nice-to-have:** Task 10 changed the live system prompt — the one part of this feature that touches every single answer, not just SP1's new block. Everything else in this plan proves references resolve correctly; nothing so far proves ordinary answers still read the same. This task closes that gap.

**Files:**
- Create: `scripts/test_sp1_answer_quality_regression.py`

**Interfaces:**
- Consumes: `generate_real_answer` (Task 8), `scripts/sp1_answer_quality_baseline.json` (written by Task 9)

- [ ] **Step 1: Write the comparison script**

```python
#!/usr/bin/env python3
"""
SP1 answer-quality regression check. Run AFTER Task 10's system_prompt.txt
edit and Task 11's chat.py wiring have both landed. Re-runs the exact same
questions from Task 9's baseline capture, through the NEW prompt, and
prints both answers side by side for manual comparison of length, tone,
and structure. This is an explicit Phase B acceptance criterion — not
optional, not a "looks fine, moving on."

Run from project root: python3 scripts/test_sp1_answer_quality_regression.py
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

from supabase import create_client
from sp1_answer_harness import generate_real_answer

SB_URL = os.environ["SUPABASE_URL"]
SB_SVC = os.environ["SUPABASE_SERVICE_KEY"]

BASELINE_FILE = Path(__file__).resolve().parent / "sp1_answer_quality_baseline.json"


def main():
    if not BASELINE_FILE.exists():
        print(f"No baseline file at {BASELINE_FILE} — run Task 9's capture script "
              f"BEFORE this comparison, or this check proves nothing.")
        sys.exit(1)

    baseline = json.loads(BASELINE_FILE.read_text())
    db = create_client(SB_URL, SB_SVC)

    for question, before_answer in baseline.items():
        after_answer, raw_output = generate_real_answer(question, db)
        assert "<reference_mentions>" not in after_answer, (
            "The <reference_mentions> block leaked into the visible answer text — "
            "this is a hard failure, stop and fix the prompt/parsing before proceeding."
        )
        print("=" * 70)
        print(f"QUESTION: {question}")
        print(f"BEFORE ({len(before_answer)} chars):\n{before_answer}\n")
        print(f"AFTER  ({len(after_answer)} chars):\n{after_answer}\n")
        print("Compare by hand: same length ballpark? same tone, structure, headings? "
              "same level of conviction and citation style?")

    print("\nReview every pair above. This check passes only when a human confirms "
          "no case reads meaningfully different in length, tone, or quality.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it and read every pair**

Run: `cd /Users/alexwhitley/rhemata && python3 scripts/test_sp1_answer_quality_regression.py`
Expected: the hard assertion never fires (no `<reference_mentions>` leakage), and for every one of the five questions, the before/after pair reads as the same quality of answer — comparable length, same tone, same structure. If any pair reads meaningfully worse or different, stop and revisit Task 10's prompt wording before continuing — this is a hard gate on Phase B, not a note-and-proceed issue.

- [ ] **Step 3: Commit**

```bash
cd /Users/alexwhitley/rhemata
git add scripts/test_sp1_answer_quality_regression.py
git commit -m "Add SP1 answer-quality regression check (before/after prompt-change comparison)"
```

---

### Task 13: Build the Track-A real-answer test harness, with the pinned question set

**Before writing questions with specific names, confirm each candidate's live servability.** This is NOT because a hidden or unlicensed teacher's name could never appear in a real answer — it can: Claude carries its own general knowledge of thousands of real teachers and can name one directly, including one this library has deliberately hidden or never licensed, even when retrieval surfaces zero content about them (see Task 7's corrected note on F.F. Bosworth). The reason to confirm servability here is different: these specific test questions are designed to exercise the FULL real pipeline — retrieval surfacing that teacher's actual citable content, the model citing them from the corpus, the writer marking the mention, the verifier resolving it — and that only happens if the teacher is genuinely retrievable. A teacher reachable only through the model's own general knowledge, with no real corpus content behind them, is a different (and already covered) check — that's exactly what Task 7's Bosworth case already proves deterministically.

Run this query for each named teacher below before finalizing the case:

```sql
SELECT s.name, s.license_status, s.visibility
FROM sources s
JOIN source_aliases a ON a.source_id = s.id
WHERE a.alias_key = '<normalized teacher name>';
```

If a candidate below turns out not to be currently servable, that case cannot exercise the full pipeline as designed — treat it the same way Task 7 already handles F.F. Bosworth (a Track-B constructed case instead), and note the substitution plainly rather than forcing a live query to match what was assumed here.

**Files:**
- Create: `scripts/test_sp1_real_answers.py`

**Interfaces:**
- Consumes: `generate_real_answer` (Task 8); `verify_references` (Task 6)

- [ ] **Step 1: Write the harness**

```python
#!/usr/bin/env python3
"""
Track-A (real-generation) test harness for SP1. Runs real questions through
the actual retrieval + Claude answer-writing path via generate_real_answer()
(same system prompt, same model, same retrieval fusion as production) — NOT
the live /chat HTTP endpoint, so no weekly-query-limit / guest-limit
metering and no conversations/messages rows are touched (per Alex's
confirmed harness choice).

IMPORTANT — per Alex's explicit instruction: a case where the model's
answer does not actually contain the targeted mention is NOT a pass by
default. If a run doesn't produce the expected mention, reword the
question and rerun until it does, THEN evaluate the verifier's output.
Do not silently count a non-materialized case as green.

Run from project root: python3 scripts/test_sp1_real_answers.py
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

from supabase import create_client
from sp1_answer_harness import generate_real_answer
from app.services.reference_verifier import verify_references

SB_URL = os.environ["SUPABASE_URL"]
SB_SVC = os.environ["SUPABASE_SERVICE_KEY"]

db = create_client(SB_URL, SB_SVC)

# Pinned test cases. "expect_mention" is the exact substring that must
# appear in the real generated answer for the case to be evaluable at all —
# if it doesn't appear, rerun with a reworded question, do not score it.
CASES = [
    {
        "id": "A1_biblical_figure_narrative",
        "question": "Walk me through the story of Paul's conversion on the road to Damascus and what it teaches about God's sovereignty in salvation.",
        "expect_mention": "Paul",
        "bar": "Zero TEACHER pointers for 'Paul'. Verse citations (e.g. Acts references), if any, may resolve as verses.",
    },
    {
        "id": "A2_ambiguous_shared_name",
        "question": "What does John Bevere teach about the fear of the Lord, and how does that connect to what the Apostle John writes about love and fear in his first epistle?",
        "expect_mention": "John Bevere",
        "bar": "Exactly one TEACHER pointer for 'John Bevere' (first full-name mention). Any bare 'John' / 'the Apostle John' biblical mention never resolves as TEACHER, even if mismarked by the writer.",
    },
    {
        "id": "A3_teacher_not_in_corpus",
        "question": "What does Kenneth Copeland teach about faith, and how does that compare to what's in this library?",
        "expect_mention": "Kenneth Copeland",
        "bar": "No TEACHER pointer, and no verified_references entry ever carries the sentinel source id (267a09ac-76f3-43fb-901f-3015aef88e22).",
    },
    {
        "id": "A4_verse_range",
        "question": "What does Romans 8:26-28 teach about the Spirit's help in our weakness?",
        "expect_mention": "Romans 8:2",  # loose match — model may write 8:26-28 or 8:26–28
        "bar": "Exactly one verified verse reference spanning the whole range (both endpoints must independently resolve).",
    },
    {
        "id": "A5_repeated_teacher_mention",
        "question": "What does Derek Prince teach about spiritual authority, and can you also summarize his overall approach to intercession?",
        "expect_mention": "Derek Prince",
        "bar": "Exactly one TEACHER pointer, anchored at the first full-name occurrence. A later short-form mention (e.g. bare 'Prince') produces no second pointer.",
    },
    {
        "id": "A6_vague_reference",
        "question": "Can you unpack what that verse about being transformed by the renewing of your mind is about?",
        "expect_mention": "renewing",
        "bar": "The model's own answer should name the real reference (Romans 12:2) explicitly rather than staying vague — if it does, that resolves normally. This case primarily checks the writer follows instructions; the verifier's robustness against genuinely vague strings is separately proven in Track B.",
    },
    {
        "id": "A7_user_mentioned_verse_named_back",
        "question": "What does Romans 8:28 mean, and how should it shape the way I process a hard season?",
        "expect_mention": "Romans 8:28",
        "bar": "The answer must explicitly name 'Romans 8:28' back in its own text — not just discuss the passage thematically without ever citing the reference (this is the writer-instruction added in Task 10, tested directly here). Once named, it must also appear in verified_references as a resolved verse pointer — this is the exact case the spec's own rationale is about: if the answer never names the verse the user asked about, there is nothing for the panel to ever trigger on.",
    },
]


def run_case(case):
    print("=" * 70)
    print(f"CASE: {case['id']}")
    print(f"Question: {case['question']}")
    print(f"Bar: {case['bar']}")
    print("-" * 70)

    answer, raw_output = generate_real_answer(case["question"], db)

    materialized = case["expect_mention"] in answer
    print(f"Target mention present in answer: {materialized}")
    if not materialized:
        print("*** NOT MATERIALIZED — reword the question and rerun. Do not score this case. ***")
        print(f"Full answer for review:\n{answer}\n")
        return {"id": case["id"], "materialized": False}

    verified = verify_references(answer, raw_output, db)
    print(f"Answer:\n{answer}\n")
    print(f"Verifier output:\n{json.dumps(verified, indent=2)}\n")

    return {"id": case["id"], "materialized": True, "answer": answer, "verified": verified}


def main():
    results = []
    for case in CASES:
        results.append(run_case(case))

    print("=" * 70)
    print("SUMMARY — review each result against its stated bar by hand.")
    for r in results:
        status = "MATERIALIZED — inspect above against the bar" if r["materialized"] else "DID NOT MATERIALIZE — rerun with reworded question"
        print(f"  {r['id']}: {status}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Before running, confirm servability for the named teachers in the pinned cases**

Run this for each of `john bevere`, `derek prince`, `kenneth copeland`:

```bash
cd /Users/alexwhitley/rhemata && python3 -c "
from dotenv import load_dotenv
load_dotenv('backend/app/.env')
import os
from supabase import create_client
db = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_KEY'])
for name in ['john bevere', 'derek prince', 'kenneth copeland']:
    r = db.table('source_aliases').select('source_id').eq('alias_key', name).limit(1).execute()
    if not r.data:
        print(name, '-> no alias found')
        continue
    sid = r.data[0]['source_id']
    s = db.table('sources').select('name, license_status, visibility').eq('id', sid).limit(1).execute()
    print(name, '->', s.data)
"
```

Expected: `john bevere` and `derek prince` show `license_status`/`visibility` that pass the gate (`public_domain`/`owned`, or `shown` with safe_mode off); `kenneth copeland` shows no alias found. If either of the first two is NOT currently servable, stop and move that case to a Track-B constructed test (same treatment as F.F. Bosworth in Task 7) rather than forcing the live case — note the substitution explicitly in Task 15's writeup.

- [ ] **Step 3: Commit the harness (before running it, since the run itself is Task 14)**

```bash
cd /Users/alexwhitley/rhemata
git add scripts/test_sp1_real_answers.py
git commit -m "Add Track-A real-answer test harness for SP1, pinned question set (incl. user-verse-naming case)"
```

---

### Task 14: Run the pinned test set, reword/rerun until every mention materializes

**Files:** none new — this task runs Task 13's script and records results.

- [ ] **Step 1: Run the harness**

Run: `cd /Users/alexwhitley/rhemata && python3 scripts/test_sp1_real_answers.py`

- [ ] **Step 2: For every case marked "DID NOT MATERIALIZE," reword the question in `scripts/test_sp1_real_answers.py` and rerun until the target mention actually appears**

This is expected to take more than one pass for at least one case — real generations vary. Do not proceed to Step 3 for a case until its target mention is confirmed present in a real answer.

- [ ] **Step 3: For every materialized case, manually inspect the printed answer + verifier output against that case's stated bar**

Record, per case, in `scripts/test_sp1_real_answers.py`'s trailing summary output or a note alongside it: pass/fail against the bar, and the exact reworded question if it changed from the pinned original.

- [ ] **Step 4: If any case produces a false resolution (a pointer that should not exist per its bar), stop — this is a hard failure of the acceptance bar, not a tuning issue to note and move past**

Return to Task 6/7 to fix the verifier logic, re-run Task 7's Track-B suite to confirm no regression, then re-run this task from Step 1.

- [ ] **Step 5: Commit the final, working question set if any wording changed during Step 2**

```bash
cd /Users/alexwhitley/rhemata
git add scripts/test_sp1_real_answers.py
git commit -m "SP1: finalize real-answer test questions after materialization pass"
```

---

### Task 15: Final acceptance check

- [ ] **Step 1: Re-run every test script from this plan in sequence, confirming all still pass together**

```bash
cd /Users/alexwhitley/rhemata
python3 scripts/test_source_resolver_relocation.py
python3 scripts/test_is_source_servable.py
python3 scripts/test_biblical_figures.py
python3 scripts/test_reference_verifier.py
python3 scripts/test_sp1_real_answers.py
```

Expected: all PASSED / all cases materialized and matching their bar, zero false resolutions anywhere.

- [ ] **Step 2: Confirm the answer-quality regression check (Task 12) was run and every pair read as unchanged quality**

This is a hard part of the acceptance bar, not a formality — go back and actually re-read Task 12's output if it wasn't reviewed carefully the first time. A feature that resolves references perfectly but degrades ordinary answers has not met Phase B's bar.

- [ ] **Step 3: Confirm the plain answer stream is unaffected — manually run one real question through the harness and read the `answer` field only, ignoring `verified_references`**

Confirm it reads exactly as a normal Rhemata answer would — no visible `<reference_mentions>` leakage, no stray tags, no truncation.

- [ ] **Step 4: Final commit closing out SP1**

```bash
cd /Users/alexwhitley/rhemata
git add -A
git commit -m "SP1: reference-pointer backend complete — writer proposes, verifier disposes, zero false resolutions confirmed"
```

SP1 is done when this commit lands with every script in Step 1 passing AND Task 12's regression check confirmed clean. SP2 (frontend panel consuming `verified_references`) is separate, unscheduled work — this plan does not include it.
