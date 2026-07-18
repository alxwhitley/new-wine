# SP4 Teacher Cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the teacher card (bio + works-in-corpus + live-synthesized position on the user's current question) and finally wire up curated teacher-name underlines in chat, per `docs/superpowers/specs/2026-07-18-sp4-teacher-cards-design.md`.

**Architecture:** A new `teacher_profiles` table (row-exists-means-curated) seeded from the 9 names already hardcoded in two frontend arrays, now all resolvable to real `sources` rows after the 2026-07-18 pre-build data fix. One combined backend endpoint (`GET /study/teacher/{source_id}`) returns bio + works + a live paraphrase-and-cite position synthesized from that teacher's own chunks, scoped by a new `match_teacher_chunks` RPC. The frontend detects curated teacher names client-side (a small, known list — not a generic NLP problem), gates underlines on SP1's existing backend verification, and renders a `TeacherCard` in the same panel surface the verse card already uses, replacing it (no nesting).

**Tech Stack:** Python 3.9 / FastAPI / supabase-py (backend), Next.js 16 / React 19 / TypeScript (frontend), Postgres/pgvector via Supabase, Anthropic `claude-sonnet-4-5`.

## Global Constraints

- **Python 3.9**: use `Optional[str]`, never `str | None` (repo invariant #1).
- **License gate SQL must be preserved verbatim** in any RPC touching `chunks`/`documents` — the exact `EXISTS (... s.license_status IN ('public_domain','owned') OR (NOT safe_mode_on AND s.visibility = 'shown') ...)` shape from migration 049/056 (repo invariant #2). `is_source_servable()` (`app/services/source_resolver.py`) is the Python equivalent — reuse it, never reimplement it.
- **No semicolons inside `--` SQL comments in migrations** — the multi-statement runner treats them as terminators and rolls back silently (repo invariant #9). Verify any new table/function with `SELECT to_regclass('public.<table>')` or `pg_get_functiondef` on a **fresh** connection, not the one that ran the DDL.
- **No MCP write tools, ever** — all DB writes (migrations, seed data) run via direct `psycopg2` against `SUPABASE_DB_URL` (`backend/app/.env`), never Supabase MCP tools. This is a hard, standing restriction in this repo, not a suggestion.
- **Never fork `normalize_alias_key`** (repo invariant #6) — the seed migration's name→`source_id` resolution must go through the real `source_aliases` table exactly as `reference_verifier.py` does, not a new ad hoc matcher.
- **No automated test framework exists in this repo.** Backend "tests" are ad hoc `scripts/test_*.py` files (a manual `check()`/`sys.exit(1)` pattern, run directly against a real Supabase connection — see `scripts/test_reference_verifier.py`). Frontend has **no** Jest/Vitest/Playwright/testing-library installed at all. Do not introduce a new framework as a side effect of this plan — follow the existing ad hoc script convention for backend, and rely on real-browser manual/Playwright-skill verification for frontend (matching every SP2 phase's own verification style).
- **Next.js 16 / React 19**: `frontend/AGENTS.md` warns this version has breaking changes from training-data expectations. This plan only reuses patterns already live and working elsewhere in this exact codebase (existing hooks, existing component shapes) — if any step feels like it needs something genuinely new from the framework, check `node_modules/next/dist/docs/` first rather than assuming.
- **Fail-quiet is a hard product rule**: no confident match = plain text, ever. For SP4 this extends to "no confident *curated* match" — a teacher SP1 resolves but that has no `teacher_profiles` row renders as plain text, never a dead or partial underline.
- **Paraphrase-and-cite only, permanently** — no LLM call in this plan may be allowed to emit verbatim quotes longer than a few words. This is a structural product posture (PLAN.md Rule 11), not a style preference.

---

## File Structure

New files:
- `migrations/064_teacher_profiles.sql` — schema + seed data
- `migrations/065_match_teacher_chunks.sql` — vector-search RPC scoped to a document set
- `backend/app/services/llm_client.py` — shared Anthropic client accessor + guardrails-text loader (extracted from `chat.py`, reused by the new endpoint)
- `scripts/test_teacher_card.py` — ad hoc verification script (this repo's established test convention)
- `frontend/components/rhemata/teacher-card.tsx` — `TeacherCard` component + `useTeacherCard` hook

Modified files:
- `backend/app/routers/chat.py` — use the extracted shared client/guardrails helpers instead of its own private copies
- `backend/app/routers/study.py` — two new endpoints (`GET /study/teachers`, `GET /study/teacher/{source_id}`)
- `frontend/lib/study-reference.ts` — extend the `teacher` variant with `source_id`, add curated-teacher detection + verification
- `frontend/components/rhemata/chat-message.tsx` — render curated teacher underlines
- `frontend/components/rhemata/study-panel.tsx` — replace the teacher-card placeholder, thread the new prop, reset Interlinear width on reference-type switch
- `frontend/app/page.tsx` — fetch the curated teacher list, widen the click handler, thread new state/props

---

### Task 1: `teacher_profiles` table + seed data

**Files:**
- Create: `migrations/064_teacher_profiles.sql`

**Interfaces:**
- Produces: table `teacher_profiles(source_id uuid PK REFERENCES sources(id), bio text NOT NULL, created_at, updated_at)`. Row existence for a given `source_id` is the sole "is this teacher curated" signal every later task reads.

- [ ] **Step 1: Write the migration file**

```sql
-- Migration 064: teacher_profiles table for SP4 (teacher card content) +
-- seed data for the 9 teachers whose bios currently live only in two
-- hardcoded, inconsistent frontend arrays (frontend/app/library/authors/page.tsx
-- AUTHORS, frontend/app/library/page.tsx AUTHOR_DATA -- same 9 names, AUTHORS'
-- bio field used here since AUTHOR_DATA has a different field, specialty,
-- instead).
--
-- Row existence = curated: a teacher's underline only ever renders live if
-- their source_id has a row here (see
-- docs/superpowers/specs/2026-07-18-sp4-teacher-cards-design.md). No new
-- teacher may be added by any path except this table -- there is no admin UI
-- for this, by deliberate scope decision.
--
-- All 9 names confirmed resolvable via source_aliases as of the 2026-07-18
-- SP4 pre-build data fix (5 of these 9 had no source_aliases row at all
-- before that fix -- see rhemata-status.md's "SP4 pre-build data fix"
-- section). Do not run this migration before confirming that fix is live
-- (SELECT count(*) FROM source_aliases WHERE alias_key IN
-- ('bob mumford','ern baxter','charles simpson','don basham','oswald j. smith')
-- should return 5).
--
-- Run manually via psycopg2 against SUPABASE_DB_URL -- no MCP write tools.

CREATE TABLE teacher_profiles (
  source_id   uuid PRIMARY KEY REFERENCES sources(id),
  bio         text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE teacher_profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "teacher_profiles: service role full access"
  ON teacher_profiles FOR ALL
  USING (auth.role() = 'service_role')
  WITH CHECK (auth.role() = 'service_role');

-- Seed data: resolves each name to source_id via source_aliases (same
-- normalize_alias_key contract -- lowercase + trim + collapse whitespace --
-- app/services/source_resolver.py). ON CONFLICT makes this idempotent.

INSERT INTO teacher_profiles (source_id, bio)
SELECT sa.source_id, v.bio
FROM (VALUES
  ('derek prince', 'Cambridge-educated philosopher turned Bible teacher, Prince founded Derek Prince Ministries after a wartime conversion and became one of the most widely translated charismatic teachers of the 20th century, known especially for his work on deliverance, healing, and the Holy Spirit.'),
  ('bob mumford', 'Bible teacher and co-founder of New Wine Magazine, Mumford is known for his Kingdom of God teaching and his role in the charismatic renewal, still living and ministering through Lifechangers.'),
  ('ern baxter', 'Canadian Pentecostal preacher regarded as one of the greatest orators of the 20th century, Baxter served as Bible teacher for William Branham''s crusades and delivered his landmark "Thy Kingdom Come" message to 5,000 leaders in Kansas City.'),
  ('charles simpson', 'Baptist-turned-charismatic pastor from Mobile, Alabama who co-founded New Wine Magazine in 1969 and became a key leader in the charismatic renewal, known for his pastoral teaching on covenant community and spiritual authority.'),
  ('don basham', 'Bible teacher and author who pioneered deliverance ministry in the charismatic movement, Basham served as editor of New Wine Magazine from 1975-1981 and was known for his accessible writing on the Holy Spirit and spiritual warfare.'),
  ('john bevere', 'Co-founder of Messenger International and bestselling author of The Bait of Satan and The Awe of God, Bevere is known globally for his bold teachings on the fear of the Lord, spiritual authority, and uncompromising discipleship.'),
  ('michael brown', 'Scholar, apologist, and radio host with a PhD from NYU, Brown is a leading charismatic voice on the Jewish roots of Christianity, revival, and cultural apologetics, and has authored over 40 books.'),
  ('jack deere', 'Former Dallas Seminary professor of Old Testament who became a charismatic theologian after encountering the gifts through John Wimber; best known for Surprised by the Power of the Spirit, a landmark defense of continuationism.'),
  ('oswald j. smith', 'Canadian pastor, hymn writer, and missions statesman who founded The People''s Church in Toronto; preached 12,000 sermons in 80 countries and was described by Billy Graham as "the greatest missionary statesman of our time."')
) AS v(alias_key, bio)
JOIN source_aliases sa ON sa.alias_key = v.alias_key
ON CONFLICT (source_id) DO NOTHING;
```

- [ ] **Step 2: Apply the migration via psycopg2**

Run (adapt the connection snippet already used in this session's DB-fix work — direct `psycopg2.connect(SUPABASE_DB_URL)`, autocommit, execute the file's SQL as one script).

- [ ] **Step 3: Verify on a fresh connection**

```sql
SELECT to_regclass('public.teacher_profiles');
-- Expected: teacher_profiles (not null)

SELECT count(*) FROM teacher_profiles;
-- Expected: 9

SELECT s.name, tp.bio FROM teacher_profiles tp
JOIN sources s ON s.id = tp.source_id
ORDER BY s.name;
-- Expected: all 9 names present, each with real bio text (spot-check 2-3
-- against the literal AUTHORS array text in
-- frontend/app/library/authors/page.tsx to confirm no seeding corruption)
```

- [ ] **Step 4: Commit**

```bash
git add migrations/064_teacher_profiles.sql
git commit -m "Add teacher_profiles table + seed 9 curated teacher bios"
```

---

### Task 2: `match_teacher_chunks` RPC

**Files:**
- Create: `migrations/065_match_teacher_chunks.sql`

**Interfaces:**
- Consumes: `chunks(id, document_id, chunk_index, content, embedding)`, `documents(id, source_id, title, author)`, `sources(id, license_status, visibility)`, `app_settings(key, value)` — all pre-existing.
- Produces: `match_teacher_chunks(query_embedding vector(1536), match_count int, document_ids uuid[]) RETURNS TABLE(id uuid, document_id uuid, content text, chunk_index int, similarity float, title text, author text)`, called via `db.rpc("match_teacher_chunks", {...})` from Task 4's endpoint.

- [ ] **Step 1: Write the migration file**

Mirrors `match_commentary_chunks`'s gated, HNSW-forced shape (migrations 041 + 056) — same CTE structure, same `set_config` calls, same license-gate `EXISTS` clause copied verbatim — but scoped by `document_ids` generally (a teacher's works can be `sermon_transcript`, `magazine_article`, etc., not just `commentary`, so there's no `source_kind` filter).

```sql
-- Migration 065: match_teacher_chunks -- vector search scoped to a specific
-- teacher's document_ids, for SP4's teacher-card position synthesis
-- (GET /study/teacher/{source_id}).
--
-- Mirrors match_commentary_chunks's gated, HNSW-forced shape (migrations 041
-- + 056) minus the source_kind='commentary' restriction -- a teacher's works
-- can be sermon_transcript, magazine_article, etc.
--
-- Defense in depth: the calling endpoint already restricts document_ids to
-- one already-is_source_servable-gated teacher before calling this, but the
-- gate is repeated here anyway (same reasoning migration 056 gave for
-- match_commentary_chunks: document_ids is a plain uuid[] parameter and
-- could in principle be called with ids that didn't come through the gate).
--
-- Run manually via psycopg2 against SUPABASE_DB_URL -- no MCP write tools.

CREATE OR REPLACE FUNCTION match_teacher_chunks(
  query_embedding vector(1536),
  match_count     int,
  document_ids    uuid[]
)
RETURNS TABLE (
  id            uuid,
  document_id   uuid,
  content       text,
  chunk_index   int,
  similarity    float,
  title         text,
  author        text
)
LANGUAGE plpgsql STABLE
AS $$
DECLARE
  safe_mode_on boolean := (
    SELECT value = 'on' FROM app_settings WHERE key = 'safe_mode'
  );
BEGIN
  PERFORM set_config('hnsw.ef_search', '200', true);
  PERFORM set_config('enable_seqscan', 'off', true);

  RETURN QUERY
  WITH nearest AS (
    SELECT
      c.id,
      c.document_id,
      c.content,
      c.chunk_index,
      1 - (c.embedding <=> query_embedding) AS similarity
    FROM chunks c
    WHERE c.document_id = ANY(document_ids)
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count
  )
  SELECT
    n.id,
    n.document_id,
    n.content,
    n.chunk_index,
    n.similarity,
    d.title,
    d.author
  FROM nearest n
  JOIN documents d ON d.id = n.document_id
  WHERE EXISTS (
    SELECT 1 FROM sources s
    WHERE s.id = d.source_id
      AND (
        s.license_status IN ('public_domain', 'owned')
        OR (NOT safe_mode_on AND s.visibility = 'shown')
      )
  );
END;
$$;
```

- [ ] **Step 2: Apply via psycopg2**

- [ ] **Step 3: Verify on a fresh connection**

```sql
SELECT proname, prosrc ILIKE '%safe_mode_on%' AS has_gate
FROM pg_proc WHERE proname = 'match_teacher_chunks'
  AND pronamespace = 'public'::regnamespace;
-- Expected: has_gate = true
```

Then a live smoke call (needs a real embedding — do this together with Task 5's test script rather than by hand; this step alone just confirms the function exists and is gated).

- [ ] **Step 4: Commit**

```bash
git add migrations/065_match_teacher_chunks.sql
git commit -m "Add match_teacher_chunks RPC, gated, scoped by document_ids"
```

---

### Task 3: Extract shared Anthropic client + guardrails loader

**Files:**
- Create: `backend/app/services/llm_client.py`
- Modify: `backend/app/routers/chat.py` (remove lines duplicating what moves; import the shared helpers instead)

**Interfaces:**
- Produces: `get_anthropic_client() -> anthropic.Anthropic`, `get_guardrails_text() -> str`. Task 4's new endpoint imports both.

**Why this is in scope:** `chat.py` already has a private `_get_anthropic()` singleton accessor and a `_guardrails_text` string (theological guardrails + a faithfulness addendum) that Task 4's position-synthesis call needs verbatim — importing a leading-underscore name across modules is the wrong shape, and duplicating the client-singleton pattern or the addendum sentence would violate this repo's "don't fork shared logic" ethic (the same reasoning behind invariant #6). This is a small, mechanical, behavior-preserving extraction, not a redesign.

- [ ] **Step 1: Create the shared module**

```python
# backend/app/services/llm_client.py
from __future__ import annotations

import os
from pathlib import Path

import anthropic

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

_anthropic_client = None
_guardrails_text = None


def get_anthropic_client():
    # type: () -> anthropic.Anthropic
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client


def get_guardrails_text() -> str:
    """Theological guardrails text, shared by every LLM call in this backend
    that represents a source document's or teacher's views (chat.py's main
    answer stream, study.py's teacher-position synthesis). Loaded once, from
    the same theological_guardrails.txt file the main answer stream has
    always used.
    """
    global _guardrails_text
    if _guardrails_text is None:
        app_dir = Path(__file__).resolve().parent.parent
        _guardrails_text = (app_dir / "theological_guardrails.txt").read_text() + (
            "\n\nRepresent the views of the source documents faithfully and accurately, "
            "even when those views reflect traditional or complementarian theology. "
            "Do not editorialize or add modern qualifications unless they appear in the source material."
        )
    return _guardrails_text
```

- [ ] **Step 2: Update `chat.py` to use the shared module**

Remove the existing block (originally at lines 188-196):
```python
_anthropic_client = None


def _get_anthropic():
    # type: () -> anthropic.Anthropic
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client
```

Remove line 43 (`ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")`).

Replace the system-prompt construction block (originally lines 55-73):
```python
_app_dir = Path(__file__).resolve().parent.parent
_system_prompt_text = (_app_dir / "system_prompt.txt").read_text()
_guardrails_text = (_app_dir / "theological_guardrails.txt").read_text() + (
    "\n\nRepresent the views of the source documents faithfully and accurately, "
    "even when those views reflect traditional or complementarian theology. "
    "Do not editorialize or add modern qualifications unless they appear in the source material."
)
ANSWER_SYSTEM_BLOCKS = [
    {
        "type": "text",
        "text": _system_prompt_text,
        "cache_control": {"type": "ephemeral"},
    },
    {
        "type": "text",
        "text": _guardrails_text,
        "cache_control": {"type": "ephemeral"},
    },
]
```
with:
```python
from app.services.llm_client import get_anthropic_client, get_guardrails_text

_app_dir = Path(__file__).resolve().parent.parent
_system_prompt_text = (_app_dir / "system_prompt.txt").read_text()
ANSWER_SYSTEM_BLOCKS = [
    {
        "type": "text",
        "text": _system_prompt_text,
        "cache_control": {"type": "ephemeral"},
    },
    {
        "type": "text",
        "text": get_guardrails_text(),
        "cache_control": {"type": "ephemeral"},
    },
]
```
(`Path` is already imported in `chat.py` — it's used by the line above already; no new import needed for that.)

Replace the call site `client = _get_anthropic()` (originally in the streaming block around line 913) with `client = get_anthropic_client()`.

- [ ] **Step 3: Check whether `import anthropic` is still needed in `chat.py`**

```bash
grep -n "anthropic\." backend/app/routers/chat.py
```
If every remaining match is inside a comment or was part of the removed block, remove the `import anthropic` line too. If `chat.py` references `anthropic.` anywhere else (e.g. exception types), leave the import in place.

- [ ] **Step 4: Manually smoke-test the main chat endpoint still works**

Start the backend locally, send one real question through `/chat`, confirm a normal streamed answer still comes back (this refactor must be a no-op for existing behavior).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/llm_client.py backend/app/routers/chat.py
git commit -m "Extract shared Anthropic client + guardrails loader from chat.py"
```

---

### Task 4: Backend endpoints — `GET /study/teachers`, `GET /study/teacher/{source_id}`

**Files:**
- Modify: `backend/app/routers/study.py`

**Interfaces:**
- Consumes: `get_anthropic_client`, `get_guardrails_text` (Task 3); `teacher_profiles`, `match_teacher_chunks` (Tasks 1-2); existing `require_user`, `get_supabase`, `embed_text`; new import `is_source_servable` from `app.services.source_resolver`.
- Produces: `GET /study/teachers -> {"teachers": [{"name": str, "source_id": str}, ...]}` (no auth). `GET /study/teacher/{source_id}?question=... -> {"bio": str, "works": [{"id": str, "title": str}, ...], "position": Optional[str]}` (requires auth, same as `/study/commentary`).

- [ ] **Step 1: Add the new imports and constants to `study.py`**

Add near the top, alongside the existing imports:
```python
from pathlib import Path

from app.services.source_resolver import is_source_servable
from app.services.llm_client import get_anthropic_client, get_guardrails_text
```

Add module-level constants (after `CORPUS_SOURCE_KINDS`):
```python
# SP4 teacher-card position synthesis. match_chunks/match_teacher_chunks
# supply no similarity threshold at all (confirmed by direct inspection of
# both RPCs' SQL, 2026-07-18 diagnostic) -- this floor is applied here,
# in Python, after retrieval. Starting default, not yet empirically tuned
# against this corpus's real query/chunk score distribution -- see Task 5's
# test script, which checks this value against a real on-topic vs.
# off-topic query before this plan is considered verified.
TEACHER_POSITION_SIMILARITY_FLOOR = 0.3

TEACHER_POSITION_PROMPT = (
    "You are summarizing what a specific teacher has said on a topic, based "
    "only on the excerpts provided below. Paraphrase in your own words — "
    "never quote more than a few words verbatim. Cite specific works by "
    "title when relevant. If the excerpts don't address the question, say "
    "so plainly rather than guessing or generalizing. Do not editorialize "
    "or add your own theological commentary — represent only what appears "
    "in the source material."
)
```

- [ ] **Step 2: Add `GET /study/teachers`**

```python
@router.get("/teachers")
async def list_curated_teachers():
    db = get_supabase()
    result = (
        db.table("teacher_profiles")
        .select("source_id, sources(name)")
        .execute()
    )
    teachers = [
        {"name": row["sources"]["name"], "source_id": row["source_id"]}
        for row in (result.data or [])
        if row.get("sources")
    ]
    return {"teachers": teachers}
```

**Verification note:** this uses PostgREST's embedded-resource select syntax (`sources(name)`), which nothing else in `study.py` currently uses (the rest of the file does plain flat `.select("col1, col2")`). Before trusting this, run it against the live REST API and confirm the nested `sources` object actually appears in the response shape expected — do not assume the syntax is correct just because it's standard PostgREST; this repo's own standing rule is verify, don't assume.

- [ ] **Step 3: Add `GET /study/teacher/{source_id}`**

```python
@router.get("/teacher/{source_id}")
async def get_teacher_card(
    source_id: str,
    question: str = Query(..., description="The user's current turn question"),
    user_id: str = Depends(require_user),
):
    db = get_supabase()

    profile_result = (
        db.table("teacher_profiles")
        .select("bio, sources(name)")
        .eq("source_id", source_id)
        .limit(1)
        .execute()
    )
    if not profile_result.data:
        raise HTTPException(status_code=404, detail="Not a curated teacher")
    bio = profile_result.data[0]["bio"]
    name = profile_result.data[0]["sources"]["name"]

    if not is_source_servable(db, source_id):
        return {"bio": bio, "works": [], "position": None}

    docs_result = (
        db.table("documents")
        .select("id, title")
        .eq("source_id", source_id)
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    works = [{"id": d["id"], "title": d["title"]} for d in (docs_result.data or [])]

    if not works:
        return {"bio": bio, "works": [], "position": None}

    try:
        embedding = embed_text(question)
    except Exception:
        logger.exception("Embedding failed for teacher-position query: %s", question[:100])
        raise HTTPException(status_code=500, detail="Embedding service error")

    document_ids = [w["id"] for w in works]
    try:
        chunk_result = db.rpc("match_teacher_chunks", {
            "query_embedding": embedding,
            "match_count": 15,
            "document_ids": document_ids,
        }).execute()
    except Exception:
        logger.exception("match_teacher_chunks RPC failed for source_id=%s", source_id)
        raise HTTPException(status_code=500, detail="Search service error")

    relevant = [
        c for c in (chunk_result.data or [])
        if c.get("similarity", 0.0) >= TEACHER_POSITION_SIMILARITY_FLOOR
    ]
    relevant.sort(key=lambda c: c["similarity"], reverse=True)
    top_chunks = relevant[:5]

    if not top_chunks:
        return {"bio": bio, "works": works, "position": None}

    excerpts_text = "\n\n".join(
        f'From "{c["title"]}":\n{c["content"]}' for c in top_chunks
    )

    try:
        client = get_anthropic_client()
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=400,
            system=[
                {"type": "text", "text": TEACHER_POSITION_PROMPT},
                {"type": "text", "text": get_guardrails_text()},
            ],
            messages=[{
                "role": "user",
                "content": (
                    f"Teacher: {name}\n\nBio: {bio}\n\n"
                    f"Excerpts:\n{excerpts_text}\n\nQuestion: {question}"
                ),
            }],
        )
        position = response.content[0].text
    except Exception:
        logger.exception("Anthropic call failed for teacher-position synthesis, source_id=%s", source_id)
        raise HTTPException(status_code=500, detail="Answer generation error")

    return {"bio": bio, "works": works, "position": position}
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/study.py
git commit -m "Add GET /study/teachers and GET /study/teacher/{source_id}"
```

---

### Task 5: Backend verification script

**Files:**
- Create: `scripts/test_teacher_card.py`

**Interfaces:**
- Consumes: live Supabase connection (same `.env`-loading pattern as `scripts/test_reference_verifier.py`), `teacher_profiles`, `match_teacher_chunks` (Tasks 1-2), `app.services.embeddings.embed_text`.
- Produces: pass/fail via `sys.exit(1)` on any failure — this is this repo's real test-running convention, not a placeholder.

**Why this test matters beyond a sanity check:** it's the one place that empirically validates `TEACHER_POSITION_SIMILARITY_FLOOR = 0.3` against this actual corpus's real score distribution, rather than leaving that constant as an untested guess — directly closing the gap the 2026-07-18 diagnostic flagged ("no similarity threshold exists anywhere in the retrieval path").

- [ ] **Step 1: Write the failing script** (fails because `teacher_profiles`/`match_teacher_chunks` don't exist yet if run before Tasks 1-2 land — run it now to confirm the failure mode, then re-run after Tasks 1-2 to confirm it passes)

```python
#!/usr/bin/env python3
"""
SP4 teacher-card verification: curated-list join, per-teacher document
counts, and the match_teacher_chunks similarity floor's real-world validity.

Run from project root: python3 scripts/test_teacher_card.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

from supabase import create_client
from app.services.embeddings import embed_text

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
db = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

failures = []


def check(name, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}")
    if not condition:
        failures.append(name)


EXPECTED_NAMES = {
    "Derek Prince", "Bob Mumford", "Ern Baxter", "Charles Simpson",
    "Don Basham", "John Bevere", "Michael Brown", "Jack Deere",
    "Oswald J. Smith",
}

# --- Curated list join ---
result = db.table("teacher_profiles").select("source_id, sources(name)").execute()
rows = result.data or []
check("teacher_profiles has exactly 9 rows", len(rows) == 9)
actual_names = {r["sources"]["name"] for r in rows if r.get("sources")}
check("all 9 expected names present", actual_names == EXPECTED_NAMES)

# --- Bob Mumford's document count matches the pre-build data fix (4 docs) ---
mumford_row = next((r for r in rows if r.get("sources", {}).get("name") == "Bob Mumford"), None)
check("Bob Mumford row found", mumford_row is not None)
if mumford_row:
    mumford_source_id = mumford_row["source_id"]
    docs_result = db.table("documents").select("id, title").eq("source_id", mumford_source_id).execute()
    mumford_docs = docs_result.data or []
    check("Bob Mumford has exactly 4 documents", len(mumford_docs) == 4)

    # --- match_teacher_chunks: on-topic query should surface real content ---
    on_topic_embedding = embed_text("What does Bob Mumford teach about the Kingdom of God?")
    doc_ids = [d["id"] for d in mumford_docs]
    on_topic_result = db.rpc("match_teacher_chunks", {
        "query_embedding": on_topic_embedding,
        "match_count": 15,
        "document_ids": doc_ids,
    }).execute()
    on_topic_chunks = on_topic_result.data or []
    check("on-topic query returns at least 1 chunk", len(on_topic_chunks) > 0)
    on_topic_scores = [c["similarity"] for c in on_topic_chunks]
    if on_topic_scores:
        check(
            f"best on-topic similarity ({max(on_topic_scores):.3f}) clears the 0.3 floor",
            max(on_topic_scores) >= 0.3,
        )

    # --- match_teacher_chunks: off-topic query should NOT clear the floor ---
    off_topic_embedding = embed_text("How do I fix my car's transmission?")
    off_topic_result = db.rpc("match_teacher_chunks", {
        "query_embedding": off_topic_embedding,
        "match_count": 15,
        "document_ids": doc_ids,
    }).execute()
    off_topic_chunks = off_topic_result.data or []
    off_topic_scores = [c["similarity"] for c in off_topic_chunks]
    # match_teacher_chunks itself has no floor -- it will still return rows.
    # What this checks is whether the ENDPOINT's 0.3 floor would correctly
    # exclude them all -- if this fails, 0.3 is the wrong value for this
    # corpus and TEACHER_POSITION_SIMILARITY_FLOOR needs adjusting before
    # this plan is considered done, not after.
    check(
        f"off-topic query's best score ({max(off_topic_scores) if off_topic_scores else 0:.3f}) stays below the 0.3 floor",
        not off_topic_scores or max(off_topic_scores) < 0.3,
    )

print(f"\n{'ALL PASSED' if not failures else f'{len(failures)} FAILURE(S): ' + ', '.join(failures)}")
if failures:
    sys.exit(1)
```

- [ ] **Step 2: Run it before Tasks 1-2 land, confirm it fails with a clear "relation does not exist" error**

Run: `python3 scripts/test_teacher_card.py`
Expected: FAIL — `teacher_profiles` (or `match_teacher_chunks`) does not exist.

- [ ] **Step 3: After Tasks 1-2 are applied, re-run and confirm every check passes**

Run: `python3 scripts/test_teacher_card.py`
Expected: `ALL PASSED`. **If the off-topic floor check fails, stop and adjust `TEACHER_POSITION_SIMILARITY_FLOOR` in `study.py` (Task 4) before proceeding to frontend work** — do not ship a floor that's empirically wrong for this corpus.

- [ ] **Step 4: Commit**

```bash
git add scripts/test_teacher_card.py
git commit -m "Add SP4 teacher-card verification script"
```

---

### Task 6: `study-reference.ts` — teacher identity + detection + verification

**Files:**
- Modify: `frontend/lib/study-reference.ts`

**Interfaces:**
- Produces: `StudyReference`'s `teacher` variant now carries `source_id: string`. New `CuratedTeacher` type, `detectTeacherReferences()`, `isTeacherVerified()`. Consumed by Task 7 (`chat-message.tsx`), Task 8 (`teacher-card.tsx`), Task 10 (`page.tsx`).

- [ ] **Step 1: Extend the `StudyReference` type**

Change:
```ts
export type StudyReference =
  | {
      type: "verse";
      raw: string;
      book: string;
      code: string;
      chapter: number;
      verseStart: number;
      verseEnd: number | null;
    }
  | {
      type: "teacher";
      name: string;
    };
```
to:
```ts
export type StudyReference =
  | {
      type: "verse";
      raw: string;
      book: string;
      code: string;
      chapter: number;
      verseStart: number;
      verseEnd: number | null;
    }
  | {
      type: "teacher";
      name: string;
      source_id: string;
    };
```

- [ ] **Step 2: Update `referenceKey` to key teachers by identity, not name string**

Change:
```ts
export function referenceKey(ref: StudyReference): string {
  return ref.type === "verse" ? `verse:${verseId(ref)}` : `teacher:${ref.name}`;
}
```
to:
```ts
export function referenceKey(ref: StudyReference): string {
  return ref.type === "verse" ? `verse:${verseId(ref)}` : `teacher:${ref.source_id}`;
}
```

- [ ] **Step 3: Update the stale header comment and the `VerifiedReference` comment**

Change the file's top comment (lines 10-13):
```ts
// Teacher-reference detection is not implemented yet — the spec's real
// mechanism (SP1's backend hidden-pointer generation) doesn't exist. Verse
// detection is the one genuinely real trigger for this session; see
// rhemata-status.md for what's deferred.
```
to:
```ts
// Teacher-reference detection (SP4): unlike verses, teacher names aren't a
// generic regex-detectable pattern — detectTeacherReferences instead does a
// literal search against the small, known curated-teacher list (fetched
// once via GET /study/teachers), then isTeacherVerified gates each match
// against SP1's backend-verified pointers by source_id, exactly like verses
// gate by identity.
```

Change the `VerifiedReference` comment (lines 177-180):
```ts
// SP1's hidden pointers, as attached to the SSE meta event's
// verified_references array (backend/app/services/reference_verifier.py).
// Only the verse shape is consumed here — SP2 has no teacher underlines
// (see the plan's Global Constraints).
```
to:
```ts
// SP1's hidden pointers, as attached to the SSE meta event's
// verified_references array (backend/app/services/reference_verifier.py).
// Both shapes are consumed as of SP4 — see isVerified (verse) and
// isTeacherVerified (teacher) below.
```

- [ ] **Step 4: Add `CuratedTeacher`, `detectTeacherReferences`, and `isTeacherVerified`**

Add after `isVerified` (end of file):
```ts
// The finite, known set of curated teachers (GET /study/teachers) — small
// enough that literal substring search is the right tool, unlike verse
// detection's regex-over-arbitrary-text problem.
export interface CuratedTeacher {
  name: string;
  source_id: string;
}

export function detectTeacherReferences(
  text: string,
  curatedTeachers: CuratedTeacher[]
): Array<Extract<StudyReference, { type: "teacher" }> & { index: number }> {
  const results: Array<Extract<StudyReference, { type: "teacher" }> & { index: number }> = [];
  for (const teacher of curatedTeachers) {
    const escaped = teacher.name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const re = new RegExp(`\\b${escaped}\\b`, "g");
    let m: RegExpExecArray | null;
    while ((m = re.exec(text)) !== null) {
      results.push({
        type: "teacher",
        name: teacher.name,
        source_id: teacher.source_id,
        index: m.index,
      });
    }
  }
  return results;
}

// Allowlist by source_id, not name string: a curated-teacher candidate the
// client detected only renders as an underline if SP1 independently
// verified the same source_id for this message. Simpler than isVerified's
// identity-parsing since both sides already carry the same source_id.
export function isTeacherVerified(
  ref: Extract<StudyReference, { type: "teacher" }>,
  verifiedRefs: VerifiedReference[]
): boolean {
  return verifiedRefs.some((v) => v.type === "teacher" && v.source_id === ref.source_id);
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/study-reference.ts
git commit -m "Extend StudyReference teacher variant with source_id; add curated-teacher detection/verification"
```

---

### Task 7: `chat-message.tsx` — curated teacher underlines

**Files:**
- Modify: `frontend/components/rhemata/chat-message.tsx`

**Interfaces:**
- Consumes: `detectTeacherReferences`, `isTeacherVerified`, `CuratedTeacher` (Task 6).
- Produces: `ChatMessageProps.onVerseClick` signature widens to `(reference: StudyReference, question?: string) => void` — Task 10 must update `page.tsx`'s `handleVerseClick` to match. New `ChatMessageProps.curatedTeachers?: CuratedTeacher[]` — Task 10 must fetch and pass this.

- [ ] **Step 1: Update imports**

Change:
```tsx
import { detectVerseReferences, isVerified, type StudyReference, type VerifiedReference } from "@/lib/study-reference";
```
to:
```tsx
import {
  detectVerseReferences,
  isVerified,
  detectTeacherReferences,
  isTeacherVerified,
  type StudyReference,
  type VerifiedReference,
  type CuratedTeacher,
} from "@/lib/study-reference";
```

- [ ] **Step 2: Widen `onVerseClick` and add `curatedTeachers` to `ChatMessageProps`**

Change:
```tsx
interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  messageId?: string | null;
  question?: string;
  accessToken?: string | null;
  onCitationClick?: (citation: Citation, index: number) => void;
  onVerseClick?: (reference: StudyReference) => void;
  /** True only while this specific message is still streaming in. Verse
   * underlines fade in only once streaming finishes (spec: "never mid-stream"). */
  isStreaming?: boolean;
  /** SP1's verified pointers for this message. A detected verse candidate
   * only renders as an underline if it matches one of these by identity. */
  verifiedReferences?: VerifiedReference[];
}
```
to:
```tsx
interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  messageId?: string | null;
  question?: string;
  accessToken?: string | null;
  onCitationClick?: (citation: Citation, index: number) => void;
  /** question is only ever populated for a teacher click (the current
   * turn's user question, for the panel's position-synthesis fetch) — verse
   * clicks call this with a single argument, same as before. */
  onVerseClick?: (reference: StudyReference, question?: string) => void;
  /** True only while this specific message is still streaming in. Verse
   * underlines fade in only once streaming finishes (spec: "never mid-stream"). */
  isStreaming?: boolean;
  /** SP1's verified pointers for this message. A detected verse candidate
   * only renders as an underline if it matches one of these by identity. */
  verifiedReferences?: VerifiedReference[];
  /** SP4: the small, known curated-teacher list (GET /study/teachers),
   * fetched once at the page level. A detected name only renders as an
   * underline if it's in this list AND SP1 verified it for this message. */
  curatedTeachers?: CuratedTeacher[];
}
```

- [ ] **Step 3: Add `TeacherReferenceSpan`**

Add after `VerseReferenceSpan` (after line 67):
```tsx
function TeacherReferenceSpan({
  reference,
  question,
  onClick,
}: {
  reference: Extract<StudyReference, { type: "teacher" }>;
  question?: string;
  onClick?: (reference: StudyReference, question?: string) => void;
}) {
  // Same visual treatment as VerseReferenceSpan — nothing in the design doc
  // calls for teacher underlines to look different from verse underlines.
  return (
    <button
      onClick={() => onClick?.(reference, question)}
      className="animate-in fade-in-0 duration-300 motion-reduce:animate-none text-foreground underline decoration-primary/50 decoration-[1px] underline-offset-4 hover:decoration-primary transition-colors cursor-pointer"
    >
      {reference.name}
    </button>
  );
}
```

- [ ] **Step 4: Wire teacher detection into `renderMessageText`**

Change the function signature:
```tsx
function renderMessageText(
  text: string,
  citations: Citation[],
  onCitationClick?: (citation: Citation, index: number) => void,
  onVerseClick?: (reference: StudyReference, question?: string) => void,
  detectVerses?: boolean,
  verifiedReferences: VerifiedReference[] = [],
  question?: string,
  curatedTeachers: CuratedTeacher[] = []
): React.ReactNode[] {
```

Insert a teacher-detection block between the existing verse-detection block and the `matches.sort(...)` line. Before (the exact current tail of the function, unchanged parts shown for anchoring):
```tsx
  if (detectVerses) {
    for (const ref of detectVerseReferences(text)) {
      if (!isVerified(ref, verifiedReferences)) continue;
      const start = ref.index;
      const end = start + ref.raw.length;
      // A verse reference should never overlap a citation marker, but stay
      // safe rather than risk mangled interleaving if it ever did.
      if (matches.some((m) => start < m.end && end > m.start)) continue;
      matches.push({
        start,
        end,
        render: () => (
          <VerseReferenceSpan key={`v-${start}`} reference={ref} onClick={onVerseClick} />
        ),
      });
    }
  }

  matches.sort((a, b) => a.start - b.start);
```
After (teacher-detection block inserted between them):
```tsx
  if (detectVerses) {
    for (const ref of detectVerseReferences(text)) {
      if (!isVerified(ref, verifiedReferences)) continue;
      const start = ref.index;
      const end = start + ref.raw.length;
      // A verse reference should never overlap a citation marker, but stay
      // safe rather than risk mangled interleaving if it ever did.
      if (matches.some((m) => start < m.end && end > m.start)) continue;
      matches.push({
        start,
        end,
        render: () => (
          <VerseReferenceSpan key={`v-${start}`} reference={ref} onClick={onVerseClick} />
        ),
      });
    }
  }

  if (detectVerses && curatedTeachers.length > 0) {
    for (const ref of detectTeacherReferences(text, curatedTeachers)) {
      if (!isTeacherVerified(ref, verifiedReferences)) continue;
      const start = ref.index;
      const end = start + ref.name.length;
      if (matches.some((m) => start < m.end && end > m.start)) continue;
      matches.push({
        start,
        end,
        render: () => (
          <TeacherReferenceSpan key={`tch-${start}`} reference={ref} question={question} onClick={onVerseClick} />
        ),
      });
    }
  }

  matches.sort((a, b) => a.start - b.start);
```

- [ ] **Step 5: Thread `question`/`curatedTeachers` through `processChildren` and its two call sites**

Change `processChildren`'s signature:
```tsx
function processChildren(
  children: React.ReactNode,
  citations: Citation[],
  onCitationClick?: (citation: Citation, index: number) => void,
  onVerseClick?: (reference: StudyReference, question?: string) => void,
  detectVerses = false,
  verifiedReferences: VerifiedReference[] = [],
  question?: string,
  curatedTeachers: CuratedTeacher[] = []
): React.ReactNode {
  if (!children) return children;

  if (typeof children === "string") {
    return renderMessageText(children, citations, onCitationClick, onVerseClick, detectVerses, verifiedReferences, question, curatedTeachers);
  }

  if (Array.isArray(children)) {
    return children.map((child, i) => {
      if (typeof child === "string") {
        return (
          <span key={i}>
            {renderMessageText(child, citations, onCitationClick, onVerseClick, detectVerses, verifiedReferences, question, curatedTeachers)}
          </span>
        );
      }
      return child;
    });
  }

  return children;
}
```

Update the `ChatMessage` component to destructure `curatedTeachers` (add to the prop list at line ~304: `curatedTeachers = [],`) and pass `question`/`curatedTeachers` at both `processChildren` call sites (the `p` and `li` component overrides):
```tsx
p: ({ children }) => (
  <p className="text-sm text-foreground leading-relaxed mb-3">
    {processChildren(children, citations, onCitationClick, onVerseClick, detectVerses, verifiedReferences, question, curatedTeachers)}
  </p>
),
...
li: ({ children }) => (
  <li>{processChildren(children, citations, onCitationClick, onVerseClick, detectVerses, verifiedReferences, question, curatedTeachers)}</li>
),
```

- [ ] **Step 6: Manually verify no TypeScript errors**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors introduced by this file's changes (pre-existing errors elsewhere, if any, are out of scope).

- [ ] **Step 7: Commit**

```bash
git add frontend/components/rhemata/chat-message.tsx
git commit -m "Render curated teacher underlines in chat, gated by SP1 verification"
```

---

### Task 8: `TeacherCard` component + `useTeacherCard` hook

**Files:**
- Create: `frontend/components/rhemata/teacher-card.tsx`

**Interfaces:**
- Consumes: `GET /study/teacher/{source_id}?question=...` (Task 4).
- Produces: `export function TeacherCard({ sourceId, question, accessToken }: { sourceId: string; question: string; accessToken?: string | null }): JSX.Element` — consumed by Task 9 (`study-panel.tsx`).

**Deviation from the design doc, made explicit rather than silent:** the design doc said the position text should reuse "whatever renders paraphrase-and-cite citations in `chat-message.tsx`" (`CitationPill`, tied to a `Citation[]` array with document/page click-through). This plan renders `position` as plain text instead — `CitationPill` requires a structured `Citation[]` array mapped to specific documents/pages, and `/study/teacher/{source_id}` returns synthesized prose, not that shape. Building that structured-citation path was never decided in brainstorming and would be new scope. The LLM prompt already asks it to "cite specific works by title when relevant" narratively, which is judged sufficient for this build; revisit if that reads as insufficient during Task 11's live verification.

- [ ] **Step 1: Write the hook + component**

Mirrors `useTeachersOnVerse`'s exact shape (`study-panel.tsx`), the established pattern for every `/study/*` fetch in this codebase (Pattern B from this plan's research — no `/study/*` call has ever gone through `lib/api.ts`).

```tsx
"use client";

import { useEffect, useState } from "react";

interface TeacherCardData {
  bio: string;
  works: Array<{ id: string; title: string }>;
  position: string | null;
}

function useTeacherCard(
  sourceId: string,
  question: string,
  accessToken: string | null | undefined
): { data: TeacherCardData | null; loading: boolean; error: boolean } {
  const [data, setData] = useState<TeacherCardData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!sourceId || !question) return;
    let cancelled = false;
    setLoading(true);
    setError(false);
    setData(null);
    const params = new URLSearchParams({ question });
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/study/teacher/${sourceId}?${params}`, {
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    })
      .then((res) => {
        if (!res.ok) throw new Error("teacher card fetch failed");
        return res.json();
      })
      .then((json) => {
        if (cancelled) return;
        setData(json);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sourceId, question, accessToken]);

  return { data, loading, error };
}

export function TeacherCard({
  sourceId,
  question,
  accessToken,
}: {
  sourceId: string;
  question: string;
  accessToken?: string | null;
}) {
  const { data, loading, error } = useTeacherCard(sourceId, question, accessToken);

  if (loading) {
    return (
      <div className="space-y-2 animate-pulse">
        <div className="h-4 w-full rounded bg-border" />
        <div className="h-4 w-5/6 rounded bg-border" />
        <div className="h-4 w-2/3 rounded bg-border" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <p className="text-sm text-muted-foreground">
        This teacher&apos;s card isn&apos;t available right now.
      </p>
    );
  }

  return (
    <div>
      <p className="text-sm text-foreground leading-relaxed">{data.bio}</p>

      <div className="mt-6">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-2">
          Works in the corpus
        </p>
        {data.works.length > 0 ? (
          <ul className="space-y-1">
            {data.works.map((w) => (
              <li key={w.id} className="text-sm text-foreground">
                {w.title}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground leading-relaxed">
            No works from this teacher are available right now.
          </p>
        )}
      </div>

      <div className="mt-6">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-2">
          Position on this question
        </p>
        {data.position ? (
          <p className="text-sm text-foreground leading-relaxed">{data.position}</p>
        ) : (
          <p className="text-sm text-muted-foreground leading-relaxed">
            No position found on this from this teacher yet.
          </p>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Manually verify no TypeScript errors**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors from this file (it isn't imported anywhere yet, so this only checks the file compiles standalone).

- [ ] **Step 3: Commit**

```bash
git add frontend/components/rhemata/teacher-card.tsx
git commit -m "Add TeacherCard component + useTeacherCard hook"
```

---

### Task 9: Wire `TeacherCard` into the Study Panel

**Files:**
- Modify: `frontend/components/rhemata/study-panel.tsx`

**Interfaces:**
- Consumes: `TeacherCard` (Task 8), `StudyReference`'s extended teacher variant (Task 6).
- Produces: `StudyPanelProps` gains `teacherQuestion?: string` — Task 10 must pass this from `page.tsx`.

- [ ] **Step 1: Import `TeacherCard`**

Add to the imports at the top:
```tsx
import { TeacherCard } from "@/components/rhemata/teacher-card";
```

- [ ] **Step 2: Add `teacherQuestion` to `PanelBody`'s props**

Change `PanelBody`'s prop destructuring/type (originally lines 181-201) from:
```tsx
function PanelBody({
  reference,
  isPinned,
  pinDisabled,
  onTogglePin,
  accessToken,
  role,
  userId,
  interlinearOpen,
  onInterlinearOpenChange,
}: {
  reference: StudyReference;
  isPinned: boolean;
  pinDisabled: boolean;
  onTogglePin: () => Promise<PinToggleResult>;
  accessToken?: string | null;
  role?: string | null;
  userId?: string | null;
  interlinearOpen: boolean;
  onInterlinearOpenChange: (open: boolean) => void;
}) {
```
to:
```tsx
function PanelBody({
  reference,
  isPinned,
  pinDisabled,
  onTogglePin,
  accessToken,
  role,
  userId,
  interlinearOpen,
  onInterlinearOpenChange,
  teacherQuestion,
}: {
  reference: StudyReference;
  isPinned: boolean;
  pinDisabled: boolean;
  onTogglePin: () => Promise<PinToggleResult>;
  accessToken?: string | null;
  role?: string | null;
  userId?: string | null;
  interlinearOpen: boolean;
  onInterlinearOpenChange: (open: boolean) => void;
  teacherQuestion?: string;
}) {
```

- [ ] **Step 3: Collapse the Interlinear width reservation when the reference isn't a verse**

Add a new effect right after the existing `selectedStrongs` reset effect (after the block ending at original line 249, `}, [verseIdStr]);`):
```tsx
  // A teacher card never has an Interlinear row — collapse the width
  // reservation if it was left open from a previously-viewed verse, so
  // switching verse -> teacher doesn't leave the panel stuck at 50vw.
  useEffect(() => {
    if (reference.type !== "verse" && interlinearOpen) {
      onInterlinearOpenChange(false);
    }
  }, [reference.type, interlinearOpen, onInterlinearOpenChange]);
```

- [ ] **Step 4: Replace the placeholder with `TeacherCard`**

Change (originally lines 362-367):
```tsx
        ) : (
          <p className="text-sm text-muted-foreground">
            Teacher cards (bio, works in the corpus, position on this topic) are a later
            piece of this build — not wired up yet.
          </p>
        )}
```
to:
```tsx
        ) : (
          <TeacherCard
            sourceId={reference.source_id}
            question={teacherQuestion ?? ""}
            accessToken={accessToken}
          />
        )}
```

- [ ] **Step 5: Thread `teacherQuestion` through `StudyPanelProps` and its call site**

Change `StudyPanelProps` (originally lines 444-454) from:
```tsx
interface StudyPanelProps {
  isOpen: boolean;
  onClose: () => void;
  reference: StudyReference | null;
  pins: StudyReference[];
  onTogglePin: (ref: StudyReference) => Promise<PinToggleResult>;
  accessToken?: string | null;
  role?: string | null;
  userId?: string | null;
  onInterlinearOpenChange?: (open: boolean) => void;
}
```
to:
```tsx
interface StudyPanelProps {
  isOpen: boolean;
  onClose: () => void;
  reference: StudyReference | null;
  pins: StudyReference[];
  onTogglePin: (ref: StudyReference) => Promise<PinToggleResult>;
  accessToken?: string | null;
  role?: string | null;
  userId?: string | null;
  onInterlinearOpenChange?: (open: boolean) => void;
  teacherQuestion?: string;
}
```

Update the function signature and the `<PanelBody>` call site (originally lines 456 and 544-554):
```tsx
export function StudyPanel({ isOpen, onClose, reference, pins, onTogglePin, accessToken, role, userId, onInterlinearOpenChange, teacherQuestion }: StudyPanelProps) {
```
```tsx
          <PanelBody
            reference={reference}
            isPinned={isPinned}
            pinDisabled={pinDisabled}
            onTogglePin={() => onTogglePin(reference)}
            accessToken={accessToken}
            role={role}
            userId={userId}
            interlinearOpen={interlinearOpen}
            onInterlinearOpenChange={handleInterlinearOpenChange}
            teacherQuestion={teacherQuestion}
          />
```

- [ ] **Step 6: Manually verify no TypeScript errors**

Run: `cd frontend && npx tsc --noEmit`
Expected: errors only about `page.tsx` not yet passing `teacherQuestion` (optional prop, so this should actually be zero errors) — if `page.tsx` errors appear here, that's expected until Task 10 lands; don't chase them in this task.

- [ ] **Step 7: Commit**

```bash
git add frontend/components/rhemata/study-panel.tsx
git commit -m "Wire TeacherCard into the Study Panel, replacing the placeholder"
```

---

### Task 10: `page.tsx` — curated teachers fetch + click-handler wiring

**Files:**
- Modify: `frontend/app/page.tsx`

**Interfaces:**
- Consumes: `CuratedTeacher` (Task 6), widened `onVerseClick` (Task 7), `teacherQuestion` prop (Task 9).
- Produces: fully wired end-to-end flow — this is the task that makes the feature actually reachable by a user.

- [ ] **Step 1: Import `CuratedTeacher`**

Change:
```tsx
import { referenceKey, referenceFromVerseId, verseId as verseIdOf, type StudyReference } from "@/lib/study-reference";
```
to:
```tsx
import { referenceKey, referenceFromVerseId, verseId as verseIdOf, type StudyReference, type CuratedTeacher } from "@/lib/study-reference";
```

- [ ] **Step 2: Add curated-teachers state + fetch, and the teacher-card question state**

Add after the existing `studyPins` state declaration (after original line 114, before the pins-fetching `useEffect`):
```tsx
  // SP4: the curated teacher list (GET /study/teachers) — public, no auth,
  // since guest users see teacher underlines too, same as verse underlines.
  const [curatedTeachers, setCuratedTeachers] = useState<CuratedTeacher[]>([]);
  // The current turn's user question, captured at teacher-underline-click
  // time (see handleVerseClick below) — the panel's live position synthesis
  // is scoped to "the user's current question," per the SP4 design doc.
  const [teacherCardQuestion, setTeacherCardQuestion] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/study/teachers`)
      .then((res) => (res.ok ? res.json() : { teachers: [] }))
      .then((data) => {
        if (cancelled) return;
        setCuratedTeachers(data.teachers ?? []);
      })
      .catch(() => {
        if (!cancelled) setCuratedTeachers([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);
```

- [ ] **Step 3: Widen `handleVerseClick`**

Change (originally lines 144-148):
```tsx
  const handleVerseClick = useCallback((reference: StudyReference) => {
    if (!isStudyPanelEnabled()) return; // defense in depth — kill switch off
    setStudyReference(reference);
    setStudyPanelOpen(true);
  }, []);
```
to:
```tsx
  const handleVerseClick = useCallback((reference: StudyReference, question?: string) => {
    if (!isStudyPanelEnabled()) return; // defense in depth — kill switch off
    setStudyReference(reference);
    setTeacherCardQuestion(question ?? "");
    setStudyPanelOpen(true);
  }, []);
```

- [ ] **Step 4: Pass `curatedTeachers` into `ChatMessage`**

Change (originally lines 471-484):
```tsx
                      <ChatMessage
                        key={i}
                        role={message.role}
                        content={message.content}
                        citations={message.citations}
                        messageId={message.messageId}
                        question={question}
                        accessToken={accessToken}
                        onCitationClick={handleCitationClick}
                        onVerseClick={handleVerseClick}
                        isStreaming={isStreaming}
                        verifiedReferences={message.verifiedReferences}
                      />
```
to:
```tsx
                      <ChatMessage
                        key={i}
                        role={message.role}
                        content={message.content}
                        citations={message.citations}
                        messageId={message.messageId}
                        question={question}
                        accessToken={accessToken}
                        onCitationClick={handleCitationClick}
                        onVerseClick={handleVerseClick}
                        isStreaming={isStreaming}
                        verifiedReferences={message.verifiedReferences}
                        curatedTeachers={curatedTeachers}
                      />
```

- [ ] **Step 5: Pass `teacherQuestion` into `StudyPanel`**

Change (originally lines 534-544):
```tsx
      <StudyPanel
        isOpen={studyPanelOpen}
        onClose={handleCloseStudyPanel}
        reference={studyReference}
        pins={studyPins.map((p) => p.reference)}
        onTogglePin={handleToggleStudyPin}
        accessToken={accessToken}
        role={userRole}
        userId={user?.id ?? null}
        onInterlinearOpenChange={setInterlinearWide}
      />
```
to:
```tsx
      <StudyPanel
        isOpen={studyPanelOpen}
        onClose={handleCloseStudyPanel}
        reference={studyReference}
        pins={studyPins.map((p) => p.reference)}
        onTogglePin={handleToggleStudyPin}
        accessToken={accessToken}
        role={userRole}
        userId={user?.id ?? null}
        onInterlinearOpenChange={setInterlinearWide}
        teacherQuestion={teacherCardQuestion}
      />
```

- [ ] **Step 6: Manually verify no TypeScript errors across the whole frontend**

Run: `cd frontend && npx tsc --noEmit`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "Wire curated teacher underlines end-to-end: fetch, click, panel"
```

---

### Task 11: End-to-end live verification

**Files:** none (verification only — this repo has no automated test runner for this surface; every SP2 phase was proven this same way, against a real deploy, not localhost, since `localhost:3000` can't reach the production backend — see the CORS note in `rhemata-status.md`)

**Interfaces:** none — this task consumes the fully wired feature from Tasks 1-10 and produces a verification record for `rhemata-status.md`.

- [ ] **Step 1: Deploy backend + frontend changes to their real environments** (Railway backend, Vercel frontend — per this repo's existing deploy flow)

- [ ] **Step 2: Verify curated vs. non-curated underlining, live**

Ask a real question on `rhemata.app` that produces an answer mentioning both a curated teacher (e.g. "What does Derek Prince teach about deliverance?") and, if possible in the same session, a name NOT in the curated list. Confirm: the curated teacher's full name is underlined after streaming completes; a non-curated name (if one appears) is plain text.

- [ ] **Step 3: Verify the card itself**

Tap the underline. Confirm: panel opens into `TeacherCard` mode (not the verse card), shows real bio text (matches Task 1's seed data), a real works-in-corpus list, and — after a brief load — a real synthesized position relevant to the question asked, with no verbatim quoting longer than a few words.

- [ ] **Step 4: Verify replace-not-nest**

With a verse card open (e.g. from a verse underline in the same answer) and Interlinear expanded (50vw), tap a teacher underline elsewhere in the same answer. Confirm: the panel replaces its content with the teacher card, and the width collapses back to 33vw (Task 9 Step 3's fix) rather than staying stuck at 50vw.

- [ ] **Step 5: Verify guest behavior**

Log out (or use a private/incognito session). Confirm curated teacher underlines still render (the `/study/teachers` list has no auth requirement), but tapping one and opening the card either shows a clear signed-out state or prompts sign-in — confirm which, and that it isn't a silently-swallowed empty state (the exact class of bug Phase 7 found and fixed in `pastors_notes.py`).

- [ ] **Step 6: Verify a teacher with zero relevant chunks for the question fails quiet**

Ask about a topic far outside a curated teacher's actual corpus content, tap their underline if one renders, confirm the position section reads "No position found..." rather than a fabricated-sounding answer — this is also where `TEACHER_POSITION_SIMILARITY_FLOOR`'s real-world behavior gets a second, live confirmation beyond Task 5's script.

- [ ] **Step 7: Record the result in `rhemata-status.md`**

Following this repo's standing rule ("shipping a fix includes correcting the record in the same session") — add an entry describing what was live-verified, any deviations found during implementation, and mark SP4 (#42) done or note what remains.
