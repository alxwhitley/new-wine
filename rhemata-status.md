# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-09 (Prince non-book curation complete across all 496
documents, trigger-teeth proof, then a read-only check of the per-document
extraction cap). No push to origin; `serving_enabled` untouched.

**Session close:** `.agents/skills/session-close/SKILL.md` (not always-loaded).
Target ≤150 lines for this file.

---

## Current state

**Derek Prince non-book quote curation — COMPLETE, all 496 documents
attempted (2026-08-09).** Two extraction batches (249, then the remaining
247), each independently re-verified against live chunk content and
manually screened for the two defect classes the automated verifier can't
catch (majority-verbatim-Scripture content; incoherent dangling fragments).
**Combined: 477 approved** (240 + 237), **20 rejected** (10 + 10, logged
to `quote_verification_log`, left `pending` — schema has no `rejected`
state), **1 untracked pre-run row** (`bc3f71fd…`) still out of scope.
Live-re-queried: Prince `approved`=477, `pending`=21, system-wide
approved=478. **Coverage gap, stated explicitly: 476/496 documents have
≥1 approved quote; 20 do not** — each of those 20's only candidate was
rejected. Extraction reached all 496; approval did not clear all 496.

**Snapshot-capture bug found and fixed, then proven with teeth.** The
extractor was storing `quote_source_revisions.passage_text` as just the
candidate span, not the full chunk — making the DB trigger's substring
check a no-op. Fixed in commit `4e3a0d1`. **Proof:** a rollback-only
transaction test inserted a fabricated quote_text two ways against a real
document — the OLD convention let it through with no exception; the FIXED
convention correctly raised the trigger's exact-substring rejection.
Zero residue confirmed after rollback. **The 239 quotes approved before
the fix were NOT regenerated** — their correctness already rests on
`verify_quote_candidate()`'s independent live check at approval time, not
the trigger's snapshot, and no live chunk-edit path exists today that
would need the snapshot to catch drift. Regenerating is optional hygiene,
not required — Alex's call.

**One-quote-per-document pattern investigated (2026-08-09, read-only, no
changes).** Every one of the 247 new candidates was the sole quote for its
document — confirmed as an **explicit, working-as-designed cap**, not
incidental truncation: `DEFAULT_PER_DOC_LIMIT = 1`
(`scripts/extract_quote_candidates_derek_prince.py:65`, `--per-doc-limit`).
The algorithm ranks every candidate across the *entire* document globally
before capping, so the one quote per document really is that document's
single best-scoring candidate — not a first-match shortcut. No code
comment or commit records why it was set to 1; the closest documented
rationale is the original quote-rail design's "50–100 first-pass quotes"
breadth-first framing (`docs/plan-archive.md`) — an inference, not a
confirmed reason. Raising it needs only `--per-doc-limit N` on a future
run (and likely `--max-attempts-per-doc` alongside it) — no code change.
Not investigated: whether more genuinely quotable material is actually
sitting unused in these chunks — a distinct question from why the cap
exists, left for Alex to decide is worth asking.

**Two flagged findings, not fixed, Alex's call:** (1) `pending` vs
`draft` — two status values doing the same job. (2) The 239 pre-fix
snapshots (addressed above).

**Confirmed this session:** no push to origin; `serving_enabled`
untouched; no teacher other than Derek Prince touched; no book-type
document touched; no code changed by the cap investigation.

**Still live (product).** ONE answer path (async; `serving_enabled` TRUE).
Quote rail live. Hidden-teacher visibility flip (Ravenhill/Savchuk/Poonen,
2026-08-09) verified against the real serving path. Position one-hop live
on origin. Book chapter extraction still 8/53; Open Decision #21 not
decided.

---

## Open blockers

**Launch:** ~68s full reveal; async concurrency unproven at 100-dial.

- Guest→account, auth CTAs, v4 props, `jewish_perspectives` drop,
  SP residuals, Hebrew lexicon grant, Lewis/Tolkien/Wilson mistag.
- Admin-panel notifications — dependency of position-refresh; no design.
- `five_fold_ministry.md` editorial marker — needs Alex.
- 20 Prince documents with zero approved quotes (coverage gap above).

---

## Next

1. **`five_fold_ministry.md` editorial decision.**
2. Async concurrency proof at 100-dial (before speed work).
3. Decide extractor hardening before any next batch — three independent
   levers now on the table: majority-Scripture/unbalanced-quote checks
   (20 rejects across two batches), the `--per-doc-limit=1` cap (raise or
   keep), and whether it's worth checking if unused material exists in
   already-processed chunks. Savchuk/Ravenhill/Poonen are eligible next.
4. Decide the 1 untracked pending row (`bc3f71fd…`).
5. Decide whether to regenerate the 239 pre-fix snapshots (optional).
6. Decide whether the 20 zero-coverage Prince documents warrant a
   targeted re-extraction (possibly informed by item 3's per-doc-limit).
7. **Human review of chapter-boundary proposals** (18 books) — Open
   Decision #21 still open.
8. **Trail / Brooks one-offs** — review then decide visibility.
9. Decide `pending` vs `draft` quote-status consolidation.
10. `jewish_perspectives` drop — needs Alex's explicit approval + a
    dedicated DB-write session.

SP: #43 swipe-to-close shipped; full drag-to-follow-with-peek not shipped.
