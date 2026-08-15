# Stabilization Track 1 Audit — 2026-08-15

## Scope and safety

This pass verified deployment, serving guards, Derek Prince quote outcomes,
stored-position evidence, deliverance attribution, and the F5 control matrix.
All production inspection was read-only. No answer was generated, no database
row was written, and `Temporary-assets/` was untouched.

Observed facts are labeled **Observed**. Conclusions that follow from code and
data but could not be tied to a retained request are labeled **Inference**.

## 1. Revision and deployment alignment

**Observed:** the two serving fixes are ancestors of local `main`:

- `21ff62fb598b5152e200cbb1c5835b60d230c447` — license/visibility gates on
  four serving surfaces.
- `bc37749` — merge containing the teacher-card bio and candidate-pool fix
  (`ceb317f`).

At verification time, `origin/main` was `be4cc010ac118969043e944c8d654832a2f68d5d`.
The local branch also contained the docs-only Track 1 design/plan commits.

**Observed:** all three production services were built from `be4cc01`, which
contains both fixes:

| Service | State | Deployment | Source revision |
|---|---|---|---|
| Railway `rhemata` | SUCCESS / RUNNING | `cbf0545e-6dd9-4305-864f-e227f8266278` | `be4cc01` |
| Railway `answer-worker` | SUCCESS / RUNNING | `a75a29dc-44a5-419b-a9e8-4dc54c7c8bef` | `be4cc01` |
| Vercel `rhemata` | READY | `rhemata-caflm26in-alxwhitleys-projects.vercel.app` | `be4cc01` |

The Railway deployments were created at `2026-08-15T21:12:53Z`. The Vercel
branch alias is `rhemata-git-main-alxwhitleys-projects.vercel.app`.

## 2. Serving-guard verification

**Observed:** `python3 scripts/test_four_surfaces_license_gate.py` passed all
10 real-database checks: servable document/article/book/background-topic/
position-paper content was returned and each matching unservable fixture was
refused. `python3 scripts/test_teacher_card_bio_redaction.py` also passed all
assertions, including the fabricated-other-teacher refusal.

**Observed:** `https://rhemata-production.up.railway.app/` returned
`{"message":"Rhemata API"}`. The exact Vercel production URL and branch alias
redirected anonymous requests to Vercel SSO. The guessed historical alias
`rhemata.vercel.app` returned `DEPLOYMENT_NOT_FOUND`; it is not the current
canonical deployment URL.

**Limitation:** this Codex task had no connected signed-in browser-control
surface. The authenticated checks for opening a servable document, refusing
the sentinel document, and rendering a Derek Prince card are therefore
access-blocked, not failed. A service-role request was deliberately not used
as a substitute for authenticated production HTTP evidence.

## 3. Derek Prince quote verification

The query ran as `rhemata_readonly_analysis`. Prince source ID:
`17be391b-d025-4178-8543-3e84da675c5d`.

**Observed:** the log covers `2026-08-08T14:04:40Z` through
`2026-08-13T20:28:04Z` and contains 1,152 decisions.

| Decision | Rule | Decisions | Documents | Distinct reasons |
|---|---|---:|---:|---:|
| accepted | `accepted` | 871 | 496 | 0 |
| refused | `db_trigger_failure` | 239 | 239 | 239 |
| refused | `subchunk_exclusion` | 21 | 8 | 1 |
| refused | `reviewer_judgment_majority_scripture` | 14 | 14 | 14 |
| refused | `reviewer_judgment_incoherent_fragment` | 6 | 6 | 6 |
| refused | `speaker_unconfirmed` | 1 | 1 | 1 |
| **Total** |  | **1,152** |  |  |

The grouped total reconciles exactly to the raw count. Current quote state is
635 approved quotes across 495 documents and 157 pending quotes across 21
documents.

**Observed:** only one current non-book, non-commentary Prince document has no
approved quote: `45adafa8-5cd7-488b-8a8b-278bf76ecf28`, *Women In The Church —
Question and Answer*. It has one incoherent-fragment refusal. The historical
“20 zero-quote documents” figure is stale.

**Decision 23 recommendation:** keep the majority-Scripture and incoherent-
fragment guards. Their refusals are narrow, legible, and account for only 20
of 1,152 decisions. Open a separate defect for the 239 `quotes_check`
constraint failures; they dominate the non-accepted outcomes and are not
evidence that the editorial guards are too strict.

## 4. Stored-position regression drift

**Observed red baseline:** the unchanged test failed 12 assertions:

- three topics were expected to return `None` because the test hardcoded Vlad
  Savchuk as hidden;
- nine returned chunks were rejected solely because Vlad Savchuk or Leonard
  Ravenhill was hardcoded as a hidden author.

All returned-chunk shape and commentary/word-study exclusion checks passed.

**Observed production state:** Derek Prince, Doug Kreighbaum, Leonard
Ravenhill, and Vlad Savchuk are all `unlicensed / shown`.

**Correction:** `scripts/test_stored_position_evidence.py` now asserts the
durable contract instead of an August 8 visibility snapshot: each topic
returns either `None` or a non-empty list; every surviving chunk has the
required shape; its current source passes `is_source_servable()`; and it is
not commentary/word-study content. The corrected test passed against all six
live topics and was committed separately as `d907bf9`.

## 5. Deliverance attribution trace

**Observed limitations:** `rhemata_readonly_analysis` lacks `SELECT` on
`answer_jobs`. A strictly read-only service-client lookup found no retained
completed job matching deliverance/demon/spiritual-warfare terms in the most
recent 100 completed jobs. The newest retained job was from August 7, and no
August 15 assistant message was retained. The exact six-citation payload
therefore cannot be replayed.

**Observed current evidence:** the current deliverance position contains 15
evidence items, all from Vlad Savchuk. Their `documents.author` values are
NULL, but `stored_position_evidence.py` resolves `sources.name` and assigns
`author = "Vlad Savchuk"` to each chunk. `producer.py` copies that field into
every citation and includes `by Vlad Savchuk` in model context. The source
panel renders `citation.author`; inline citation pills render only `[n]`.

**Inference:** the likely earliest loss is generation, not evidence or the
source-panel renderer. The generation constraint at
`backend/app/services/async_answers/producer.py:452` limits which names may be
used but does not require a grounded teacher name to appear. A fully anonymous
answer can therefore pass the attribution guard. Inline `[n]` pills then make
the omission visible until a reader opens the source panel.

**Track 2 discriminating test:** construct one citable, single-author evidence
bag whose citation has `author = "Vlad Savchuk"`; make generation return prose
with citations but no author name; assert the answer is regenerated once or
deterministically labeled, while multi-author and genuinely anonymous sources
retain their existing behavior. The fix must be independently reviewed and
mutation-proven because it changes the answer path.

## 6. F5 reconstruction and classification

The original Grok 19-finding file:line artifact was not recoverable from the
repository, Git history, retained worktrees, audit files, or this task's
terminal state. The table below is a bounded reconstruction of the current
control matrix. It is authoritative for current code, but it cannot honestly
claim one-to-one identity with the missing original numbering.

| # | Surface/control | Current evidence | Status | Owner / revisit trigger |
|---:|---|---|---|---|
| 1 | Async answer license/visibility | Retrieval RPC gates plus stored/background/paper live gates | closed | Backend; mutation regression |
| 2 | Async commentary exclusion | `producer.py:331`, repeated after neighbor expansion | closed | Backend; regression |
| 3 | Async attribution grounding | `producer.py:729`, regenerate once then refuse | closed | Backend; regression |
| 4 | Async reference verification | `producer.py:746` | closed | Backend; regression |
| 5 | Async position-paper fence | bounded context plus contradiction exclusion | closed | Backend; pillar changes |
| 6 | Async quote rail | verified IDs selected at `producer.py:774-778` | closed | Backend; quote-path changes |
| 7 | Teacher-card license/visibility | `study.py:1020` | closed | Backend; regression |
| 8 | Teacher-card commentary exclusion | `study.py:1051` | closed by `21f5b14` lineage | Backend; regression |
| 9 | Teacher-card attribution grounding | regenerate/refuse guard in `study.py` | closed by `21f5b14` lineage | Backend; regression |
| 10 | Teacher-card position-paper fence | Deliberately not applied: substituting house prose would misrepresent the named teacher | accepted | Alex; revisit only if card semantics change |
| 11 | Teacher-card quote verification/rail | Card returns paraphrased position, not approved quote text | accepted | Alex; revisit if quotes are added to cards |
| 12 | Document reader | `document.py:19` gate | closed by `21ff62f` | Backend; regression |
| 13 | Article reader | `document.py:57` gate | closed by `21ff62f` | Backend; regression |
| 14 | Book excerpt reader | `library.py:104` gate | closed by `21ff62f` | Backend; regression |
| 15 | Background-topic injection | `producer.py:497/550` gate | closed by `21ff62f` | Backend; regression |
| 16 | Position-paper body load | `position_papers.py:1022/1055` gate | closed by `21ff62f` | Backend; regression |
| 17 | Search/browse corpus | gated retrieval RPCs; direct browse uses `_gated_source_ids()` | closed | Backend; RPC/browse changes |
| 18 | Separate word-study/lexicon surfaces | Deliberate non-answer study tools; Precept Austin remains excluded from answer/paraphrase paths | accepted | Alex; legal/surface-scope change |
| 19 | Document-writing ingest chokepoint | `shared_ingest.py:341` covers normal writers; `backend/app/routers/ingest.py:99` writes directly | accepted exception | Alex; delete or rebuild endpoint if reactivated |
| 20 | Failure reconciliation | Worker exceptions include worker and job IDs (`scripts/answer_worker.py:177`); `/ingest` logs only a generic endpoint exception (`ingest.py:130`) | needs-build | Backend; before F5 close |

Rows 12–16 are the later license/visibility findings and do overlap the
control areas implicated by the original trace, but missing trace provenance
prevents a defensible claim about exactly how many of the original 17 they
close.

**F5 verdict: UNMET.** The live answer path now has all named safety guards,
but the criterion remains open because the accepted PDF-ingest exception
literally bypasses the sole writer, generic ingest failure logging does not
support packet/source reconciliation, and the original finding-to-fix mapping
cannot be reconstructed one-to-one.

## 7. Track 2 packets, in order

1. **Quote constraint failure:** reproduce one of the 239 `quotes_check`
   failures against the current schema, identify the violating field, and add
   a mutation-sensitive regression before changing verifier/storage code.
2. **Single-author attribution contract:** add the discriminating deliverance
   fixture described above; choose regeneration versus deterministic label
   only after the failing test identifies the narrowest safe point.
3. **F5 ingest observability:** include endpoint/job/source/document identity
   in failure records and logs without secrets; prove a failed packet can be
   reconciled from durable state.
4. **Read-only analysis permission:** grant or deliberately refuse
   `answer_jobs` read access to `rhemata_readonly_analysis`; this is a separate
   production DB-write session with before/after privilege proof.
5. **Authenticated UI smoke:** connect a signed-in browser and verify the
   servable document, sentinel 404, and Derek Prince card on the exact READY
   Vercel deployment.
6. **F5 provenance:** if the original Grok output can be recovered from the
   external task transcript, map it to this matrix; otherwise explicitly
   replace the stale “19/17” narrative in the governing records with this
   reconstructed matrix after Alex's review.

No doctrinal content or position-paper prose was changed in this track.
