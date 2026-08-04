# HistoricalChristianFaith Attribution Re-verification + C.S. Lewis Copyright Finding

**Date:** 2026-08-04
**Type:** read-only audit — SELECT-only live queries + repo/code read + git history. **Zero writes, zero re-ingestion, nothing changed.**
**Scope:** (1) the 307 documents in the `HistoricalChristianFaith Commentaries Database` source (`sources.id 2ec56c5f-8670-4824-ac2e-e9aa7485b03d`) alleged to have "stripped attribution"; (2) the document attributed to C.S. Lewis filed as out-of-copyright.
**Relationship to prior work:** re-verifies and extends `docs/audits/historical_commentary_attribution_and_copyright_audit_2026-07-31.md`. All figures below re-queried live 2026-08-04 — **no drift** from the 2026-07-31 audit.

---

## TASK 1 — the 307 "stripped attribution" commentary documents

**Source (live):** `HistoricalChristianFaith Commentaries Database`, `license_status=public_domain`, `visibility=shown`, `retrievable=true`, slug `historicalchristianfaith`. **307 documents.**

### Finding: attribution is NOT stripped — the premise is mistaken

| Check (live 2026-08-04) | Result |
|---|---|
| Docs with non-empty `author` | **307 / 307** |
| Docs with NULL/empty/generic author | **0** |
| Distinct author values | **307** (one document per author) |

Per document, `author == title == original_title` = the same real name (e.g. `CS Lewis`, `Augustine of Hippo`, `John Chrysostom`). The author name is fully present in our own data for every one of the 307. Nothing was anonymized or lost from the author field.

### Recoverability breakdown (exact counts, as requested)

| Bucket | Count | Basis |
|---|---:|---|
| **Recoverable from existing data** | **307 / 307** | Author name already stored in `documents.author` (= `original_title`). Nothing to recover — it is in the DB now. |
| Recoverable by re-fetching original source | **0** | N/A — nothing missing. (Also impossible: the original `/tmp` SQLite dump the retired `ingest_commentaries.py` read is gone; `url`/`file_path`/`full_text` are NULL on all 307.) |
| Not recoverable at all | **0** | — |

### Ingest bug, or already anonymous? — Neither

The source material was **attributed** (each entry is a named author), and the ingest **captured the author name correctly** into `documents.author`. The one real historical ingest bug was unrelated to the author field: the importer hardcoded `citation_mode='citable'` (wrong for commentary); that was already corrected to `silent_context` on all 307 (verified live; no migration/commit trail — an undocumented manual SQL UPDATE, per the 2026-07-31 audit).

### What is actually going on (the real, separate issues — not lost attribution)

1. **Serve-time suppression, not lost data.** All 307 carry `citation_mode='silent_context'`, so in **chat answers** they render as unattributed `[Background]`. Deliberate — and moot, since commentaries are excluded from answers by policy (Alex, 1 Aug; CLAUDE.md decision #5) and none has propositions (`props=0`). This is the likely origin of the "stripped attribution" impression: a user looking at chat behavior sees no name, but the name is in the DB the whole time.
2. **Author is text metadata, not a first-class entity.** All 307 share **one** `source_id` (the collection); the individual author lives in the `documents.author` text field, not as its own `sources`/teacher row — so it cannot be independently license-gated or resolved as a citable teacher. The only sense in which a name "didn't make it into a field": present as text, absent as an entity.
3. **No stored raw provenance.** `file_path`, `url`, `full_text`, `source` are NULL on all 307 (only `source_type`/`source_name`/`original_title` populated). The document text survives in `chunks`; what is gone is any pointer back to the origin file/URL, and the original SQLite input itself.

---

## TASK 2 — the C.S. Lewis document

**Document** `caedc32c-1fb4-4be4-859c-13336d585e49` — `author='CS Lewis'`, `title='CS Lewis'`, `year=1963`, in the HistoricalChristianFaith source, `source_kind=commentary`, `citation_mode=silent_context`, `is_copyrighted=false`, `url`/`file_path` NULL, **705 chunks**.

### What it actually is

A **verbatim compilation of C.S. Lewis's own prose**, arranged as a Bible-verse commentary catena — each excerpt tagged with its work + the verse it is mapped to, stored as verbatim full-text chunks (not paraphrase). First chunk, verbatim:

> *"Mere Christianity, Book 3, Chapter 11: Faith (1chronicles 29000014): Every faculty you have, your power of thinking or of moving your limbs from moment to moment, is given you by God…"*

Unmistakably Lewis's actual text from *Mere Christianity* (in print, actively licensed by the C.S. Lewis Company / HarperOne).

### Copyright status tagged, and why

- **Source-level:** `license_status='public_domain'`, `visibility='shown'`, `retrievable=true`. Lewis inherits this because the entire HCF collection was ingested under **one** source row blanket-tagged public domain (the collection is overwhelmingly patristic/PD). The schema has **no per-document/per-author license field** — `documents` has no `license_status`/`visibility` of its own (those columns exist only on `sources`), so Lewis structurally cannot be marked differently from Augustine within this source.
- **Document-level:** `is_copyrighted=false` — the folder-path-derived flag CLAUDE.md Invariant 4 documents as unreliable and which the retrieval gate ignores on purpose.

### Is the PD tag defensible? — No

C.S. Lewis died 22 Nov 1963; under life+70 his works are protected until end of 2033 (UK/EU), and *Mere Christianity* is commercially licensed today. Tagging it `public_domain` is factually wrong and indefensible. Because the retrieval gate keys on the **source's** `public_domain` status (CLAUDE.md Invariant 2, first arm — passes regardless of safe_mode), this verbatim in-copyright text is currently retrievable.

### Misattribution, or correct author / wrong tag? — Correct author, wrong copyright tag

The content is genuinely C.S. Lewis (verbatim *Mere Christianity*) — not attributed to the wrong person. The defect is purely the copyright classification, compounded by verbatim full-text storage of protected material.

### Live exposure surface (confirmed 2026-08-04)

- `/study/commentary` (`backend/app/routers/study.py`) **deliberately applies no `citation_mode` filter** (code comment: *"always shown in Study Mode. Do not add a citation_mode filter here"*); the RPCs apply the license gate, which the `public_domain` HCF source passes; `frontend/components/rhemata/commentary-accordion-row.tsx:62` renders `{r.author}`. So **Study Mode shows the Lewis excerpts by name**. (The file's uncommitted working-tree change is a cosmetic spacing tweak; it does not affect author display.)
- The admin **"Historical Commentaries"** toggle (`source_toggles`, `source_kind=commentary`) is **`enabled=true`** live — the 307 are currently shown; flipping it to disabled removes all 307 from Study retrieval with no schema change.

### Same class — two identical siblings (verified live)

| Author | Doc | Status | `year` | Source license/vis |
|---|---|---|---|---|
| **C.S. Lewis** | 1 | d. 1963 → protected ~2033 | 1963 | public_domain / shown |
| **J.R.R. Tolkien** | 1 | d. 1973 → protected ~2043 | 1973 | public_domain / shown |
| **Douglas Wilson** | 1 | **living** (b. 1953) | 2020 | public_domain / shown |

The other ~304 authors are ancient/medieval/Reformation-era, not a copyright concern; their exact death years were not individually re-verified (same era-bucket simplification as the 2026-07-31 audit).

---

## Recommendations (not acted on — read-only session)

**TASK 1 — attribution.** Take "stripped attribution / recover the names" off the list — **there is nothing to recover**; all 307 names are intact in `documents.author`. Open blocker #15's original premise ("importer set citable; unknown whether the names survived") is resolved: names survived in full; the `citable → silent_context` change is a correct, applied setting. The only residual worth a future decision (and only if a real need arises) is structural: whether these 307 authors should ever become first-class `sources`/citable entities, and the fact that raw provenance (`url`/`file_path`/`full_text`) and the original SQLite source are gone. Neither is urgent; both are deferred-growth items (PLAN.md #12/#27).

**TASK 2 — C.S. Lewis (and Tolkien / Wilson).** A live problem: verbatim in-copyright text under a `public_domain` source, retrievable and shown by name in Study Mode. Interim, do the reversible thing first — flip the **"Historical Commentaries"** `source_toggles` row to `enabled=false` to pull all 307 out of Study retrieval pending a real fix (fastest, no schema change, no data loss). The durable fix is a **per-author/per-document license override**; the current source-level-only license model has no way to mark three rights-holders differently from Augustine inside one collection source — that schema decision is the actual blocker and is Alex's call. Do not silently delete the three rows: the exposure is the source-level PD tag + verbatim storage, so the decision (pull vs. re-license vs. schema override) should be deliberate.
