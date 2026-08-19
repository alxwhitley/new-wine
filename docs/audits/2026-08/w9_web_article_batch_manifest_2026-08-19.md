# W9 Web-Article Batch Manifest — 2026-08-19

**Status:** Staging hidden; **3 Vlad previews ready**; Lana item quarantined.  
**Paused for write clearance** on the active trio below.

## Locked decisions

| Field | Value |
|---|---|
| Teacher / site | Vlad Savchuk / pastorvlad.org |
| Count | **3** |
| Staging source | `33cfa6b5-ae98-4c68-a41a-e1db52914546` — **Vlad Savchuk (web staging)** (`unlicensed`) |
| Quote writes | **None** this batch |
| Worker deploy | **No** — attended `scripts/source_ingest_worker.py --once --row-id` only |
| Bare `--once` drain | **Forbidden** |

## Immutable URL list (active write set)

| # | Canonical URL | Title (page) | Notes |
|---|---|---|---|
| 1 | `https://pastorvlad.org/tenways/` | 10 Ways to Know the Holy Spirit Better | Byline **Vlad**; HS relationship |
| 2 | `https://pastorvlad.org/planted-not-buried-what-god-is-doing-while-you-wait/` | Planted Not Buried: What God Is Doing While You Wait | Byline **Vlad**; formation / waiting |
| 3 | `https://pastorvlad.org/signs-the-enemy-is-attacking-your-mind-and-how-to-fight-back/` | Signs the Enemy Is Attacking Your Mind and How to Fight Back | Byline **Vlad**; mind attack — **replacement** |

### Quarantined / rejected from this batch

| URL | Reason |
|---|---|
| `…/intrusive-thoughts-demon-stronghold-or-just-your-mind/` | Byline **Lana Savchuk**; row `fd16372d-…` → `needs_attention` |
| `…/strongholds-in-the-mind-…` (candidate only) | Also Byline **Lana** — never enqueued |

Excluded otherwise: W5 prayer-language article; e-courses; reading plans; books.

## Per-row slots (after enqueue + preview)

| # | Queue row UUID | Preview report id | Chunks | Props | Quote proposals | Result document id | Notes |
|---|---|---|---|---|---|---|---|
| # | Queue row UUID | Doc id | Chunks | Props / elig | attempted/stored/skipped/errored | Notes |
|---|---|---|---|---|---|---|
| 1 | `2f18306f-…` | `3d261c1d-…` | 3 | 10 / 0 | 1/1/0/0 | tenways — **written** |
| 2 | `c2f52424-…` | `9ab8961a-…` | 3 | 6 / 0 | 1/1/0/0 | planted — **written** |
| 3 | `fbcc5a42-…` | `f0450315-…` | 5 | 8 / 0 | 1/1/0/0 | mind-attack — **written** (preview had 6 props; write 8) |
| — | `fd16372d-…` | — | — | — | — | Lana — `needs_attention`, not written |

**Hard reconcile (batch rows):** attempted=3 stored=3 skipped=0 errored=0.  
**Staging docs:** 4 (W5 + 3). Staging still **`hidden`**. Live Vlad `shown`.  
Log: `docs/audits/w9_batch_log_2026-08-19.jsonl`.

## Visibility window (Alex: “just make it visible”)

Product quarantine waived (no users). **Code still requires `hidden` to write.**

1. Flip staging `shown` → `hidden` for the write window only.
2. Preview → clear → pinned write ×3.
3. Eligibility sample (W5 taste pattern).
4. Flip staging → `shown` promptly.
5. Existing W5 article is unretriable only during the brief hidden window — accepted.

## Cost band (before paid work)

Scaled from W5 (~1.3k-word article; embed ~2.5k tok; extract ~4.5k tok; $ ≪ $1;
human review dominant):

| | ×1 | ×3 batch |
|---|---|---|
| Embeddings (order) | ~2.5k tok | ~7.5k |
| Prop extract gpt-oss-120b (order) | ~4.5k tok | ~13.5k |
| Provider $ | ≪ $1 | **well under $50 ceiling** |
| Human time | 1 eligibility pass | **~3× W5** (real limiter) |

Re-estimate if any capture is much longer than W5.

## Resume / reconcile rules

- Append-only JSONL log at run time (e.g. `docs/audits/w9_batch_log_2026-08-19.jsonl`).
- Only claim cleared UUIDs from this manifest via `--once --row-id`.
- Skip rows already terminal in log / queue `done`.
- Hard reconcile: ∑attempted / ∑stored / ∑skipped / ∑errored vs live docs on
  staging source (expect +3 docs if all store; W5 doc remains).
- Stop on mismatch, clearance violation, or unexpected extra document.

## Quality sample + release

- Eligibility: KEEP yield/habit/faith-order/secret-place style claims; DROP
  technique sprawl / disclaimer lists (W5 pattern).
- Integrity: at least one teacher-named retrieval or async smoke on a new
  article (avoid bare how-to tongues phrasing → position-paper match).
- Explicit release = staging `shown` after sample + Alex OK.

## Non-goals

Quote pipeline; Invariant 16 gate change; other teachers; unpinned drain;
PITR drill; renaming “(web staging)” display (optional later).

## Sign-off

- [x] URL trio approved (Alex, chat)
- [x] Cost band + visibility window accepted → enqueue/preview done
- [x] Item 3 Lana quarantined; Vlad mind-attack replacement previewed
- [x] Accept active trio (#1–#3 Vlad) → clear + pinned write (3/3/0/0)
- [x] Staging → `shown` (eligibility deferred)
- [x] Batch write/release audit:
  `docs/audits/w9_web_article_batch_write_2026-08-19.md`
