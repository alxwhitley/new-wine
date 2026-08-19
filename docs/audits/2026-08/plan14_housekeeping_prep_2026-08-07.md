# PLAN #14 housekeeping prep (read-only)

**Date:** 2026-08-07  
**Scope:** Inventory only — **no renames, no DROP applied.**  
**PLAN item:** Phase 5 `#14` — folder renames (`lexicon/`→`stepbible/`,
`documents/`→`inbox/`) + drop `jewish_perspectives`.

This doc is the exact change set a later session can execute after Alex
approves. Do not treat presence of this file as authorization to act.

---

## 1. `jewish_perspectives` — safe to drop (after approval)

### Runtime code

**Zero** reads/writes in `backend/`, `scripts/`, or `frontend/` (2026-08-07
repo-wide search). Product surface never queries this table.

### Schema history (migrations only)

| Migration | What it does |
|---|---|
| `022_jewish_perspectives.sql` | `CREATE TABLE` + index + RLS policies |
| `027_clear_jp_cache.sql` | `DELETE FROM jewish_perspectives` (cache clear) |
| `037_rls_all_tables.sql` | Comment mention only (table listed in header prose) |

### Live DB (read-only probe 2026-08-07)

- Table exists.
- **2 rows** (`count=2`).
- Columns: `id`, `verse_reference`, `content`, `generated_at`, `model`.

### Draft migration (DO NOT APPLY until Alex says so)

Suggested next number: **`084_drop_jewish_perspectives.sql`** (after
`083_quote_rail_answer_jobs_wiring.sql`).

```sql
-- Migration 084: Drop unused jewish_perspectives cache table (PLAN #14).
-- Precondition (verified 2026-08-07): zero application code references;
-- 2 residual rows; no product surface reads this table.
-- Apply only with Alex's explicit approval. Plain-script path only (DB write).

DROP POLICY IF EXISTS "Anyone can read jewish_perspectives" ON jewish_perspectives;
DROP POLICY IF EXISTS "Service role can insert jewish_perspectives" ON jewish_perspectives;
DROP POLICY IF EXISTS "Service role can update jewish_perspectives" ON jewish_perspectives;
DROP INDEX IF EXISTS idx_jewish_perspectives_verse;
DROP TABLE IF EXISTS jewish_perspectives;
```

**Post-apply checks (on a fresh connection):**

```sql
SELECT to_regclass('public.jewish_perspectives');  -- expect NULL
```

**Docs to update when applied:** PLAN.md #14 line, rhemata-status blockers
list. Historical migrations `022`/`027` stay as-is (never rewrite history).

---

## 2. Folder renames — blast radius is small but real

`sources/` is **gitignored** (`/.sources/` in `.gitignore`), so renames are
**local filesystem + path-string edits only** — not a git content move of the
data files themselves. Collision check 2026-08-07: `sources/stepbible` and
`sources/inbox` do **not** exist yet.

### Current layout (relevant)

```
sources/
  lexicon/          # STEPBible TSVs + TAGNT interlinear files (see list below)
  documents/        # PD papers + ingested/ subdir
  Interlinear/      # separate capital-I dir — NOT part of #14 rename
  youtube/, web/, magazine/, precept_austin/, ...
```

**`sources/lexicon/` contents** (why `stepbible/` is a better name): holds
TBESG/TBESH/TFLSJ **and** TAGNT/TAHOT amalgamated text — not only “lexicon”
files. `ingest_interlinear.py` already points `LEXICON_DIR` here for TAGNT.

**`sources/documents/` contents:** three position-paper markdowns, plus
`ingested/` (post-ingest parking).

### Code path rewrites required (runtime / scripts)

| File | Current | Change to |
|---|---|---|
| `scripts/ingest_lexicon.py:50` | `PROJECT_ROOT / "sources" / "lexicon"` | `... / "stepbible"` |
| `scripts/ingest_lexicon.py` docstring L4 | `sources/lexicon/` | `sources/stepbible/` |
| `scripts/ingest_interlinear.py:27` | `... / "lexicon"` | `... / "stepbible"` |
| `scripts/ingest.py:504–506` | default scan `DOCS_FOLDER / "documents"` + comment | `... / "inbox"` |
| `scripts/scrape_ccel.py:6,25` | `sources/documents` | `sources/inbox` |
| `scripts/download_corpus_batch3.py:2,7` | `sources/documents` | `sources/inbox` |

`scripts/ingest_lexicon_runner.py` uses `ingest_lexicon.LEXICON_DIR` — **no
hardcoded path**; updates automatically when `ingest_lexicon.py` changes.

### Do **not** rename these (false positives)

These mention the word “lexicon” or “documents” but are **DB `source_kind`**,
SQL, or unrelated:

- `source_kind = 'lexicon'` (chat, study, library, migrations, admin corpus-data)
- `SOURCE_KIND_FUSION_WEIGHTS["lexicon"]`
- `documents` table / JOIN comments in SQL
- Frontend library API path `/search/documents/browse`
- `sources/Interlinear/` (different directory; out of #14 scope)

### Docs / comments (non-blocking but should land in same rename commit)

| File | Note |
|---|---|
| `ARCHITECTURE.md:18` | Tree still says `documents/` — update to `inbox/` + add `stepbible/` |
| `PLAN.md` #14 line | Collapse to DONE when executed |
| `rhemata-status.md` | Remove `jewish_perspectives` drop from open blockers when dropped |
| Historical audits under `docs/audits/` | Leave as historical; do not mass-rewrite |

### Shell sequence (after path edits are ready)

Run from repo root, **only after** the script path strings above are updated
(or in the same commit so nothing points at the old names mid-flight):

```bash
# 1. Confirm no collision
test ! -e sources/stepbible && test ! -e sources/inbox

# 2. Rename (local only; sources/ is gitignored)
mv sources/lexicon sources/stepbible
mv sources/documents sources/inbox

# 3. Smoke
python3 -c "from pathlib import Path; import sys; sys.path.insert(0,'scripts'); \
  import ingest_lexicon; print(ingest_lexicon.LEXICON_DIR, ingest_lexicon.LEXICON_DIR.is_dir())"
ls sources/stepbible | head
ls sources/inbox | head
```

Do **not** run a full lexicon re-ingest as part of the rename.

---

## 3. Recommended execution order (later session)

1. Alex approves: rename only / drop only / both.  
2. **Repo-only commit:** path string updates + `ARCHITECTURE.md` tree.  
3. **Local shell:** `mv` the two directories (not in git).  
4. **DB-write session (plain path, never harness):** apply draft `084` if
   drop approved; verify `to_regclass` is NULL.  
5. PLAN / status collapse to DONE.

Two isolated commits still apply: build/path edits separate from any
docs-only residual if preferred; the DROP is never a code commit — it is a
migration apply on the plain path.

---

## 4. Out of scope for #14 (noted, not done)

- Pinning unpinned `pydantic`/`starlette` (separate landmine; needs prod version probe first).
- `#13` helloao conversion.
- One-hop position injection.
- Deleting local `recovery/` backups (tracked files exist; never delete without explicit ask).
- `sources/Interlinear/` rename or merge into `stepbible/`.

---

## Provenance

- Live `jewish_perspectives` count: Supabase REST read 2026-08-07.
- Path inventory: repo walk of `.py`/`.md`/`.sql` excluding plan-archive and local review queues.
- Push same day: matcher + PLAN v6 commits already on `origin/main`.
