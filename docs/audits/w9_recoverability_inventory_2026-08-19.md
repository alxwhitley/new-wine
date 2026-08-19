# W9 Recoverability Inventory — 2026-08-19

**Outcome for this pass:** record authoritative backup/PITR facts, restore
granularity, known exclusions, and what still needs Alex's acceptance.
**Non-goals:** no restore drill, no staging project, no web-article batch
(PLAN.md W9 second bullet), no Plan.md rewrite until session close.

**Sources for this inventory:**

1. Live Supabase Dashboard → Database → Backups screenshot (Alex, 2026-08-19).
2. Current Supabase docs: [Database Backups](https://supabase.com/docs/guides/platform/backups).
3. Repo history: `docs/plan-archive.md` (#1 sources Drive backup; #15 record-level
   restore); scripts `export_restore_document.py` / `fingerprint_document.py`.

---

## Authoritative project backup state (dashboard-verified)

| Field | Value | Evidence |
|---|---|---|
| Project ref | `jjerxncanaxlbdzcybab` | `SUPABASE_URL` in `backend/app/.env` |
| Scheduled daily backups | **Enabled** | Dashboard "Scheduled backups · Enabled" |
| PITR | **Disabled** | Dashboard "Point in Time · Point-in-Time Recovery (PITR) is not enabled" |
| Backup type | **Physical** | Dashboard: "Your project is using Physical Backups…" |
| Approx DB size | ~10.6 GB | Latest backup 10.65 GB |
| Visible restore points | **7 daily** (Aug 12–18, 2026, 00:00 UTC) | Dashboard list |
| Latest backup | **Aug 18, 2026 00:00 UTC** (10.65 GB) | Dashboard |
| Restore action | **Available** on each listed daily backup | Dashboard "Restore" |
| Retention (inferred) | **7 days** of daily backups | Matches Pro-plan default (7 visible days; Team would show 14) |

**Plan inference (not a separate dashboard field in the screenshot):** seven
consecutive midnight-UTC daily backups and no PITR matches Supabase **Pro**
daily-backup retention. Confirm org/plan label in Billing if a Team/Enterprise
upgrade ever changes this.

---

## Restore granularity and implied RPO/RTO

### What the platform can do today (PITR off)

- **Granularity:** whole daily physical snapshot at **00:00 UTC**.
- **Implied RPO (worst case):** up to **~24 hours** of writes after the last
  completed daily backup — anything written after that midnight is not on a
  scheduled restore point until the next night's backup.
- **Restore scope:** project-level restore of the database to a chosen daily
  backup (Dashboard restore). Project is **inaccessible during restore**;
  downtime scales with DB size (~10.6 GB → expect non-trivial minutes, not
  seconds; exact duration **unmeasured**).
- **Implied RTO:** **UNVERIFIED** — no timed project restore has been run.
  Record as "unknown until first drill or Alex accepts unproven RTO."

### What PITR would add (not enabled)

Per Supabase docs (not live on this project):

- Restore to a chosen point with up to **seconds** of granularity.
- WAL archived about every **two minutes** → documented worst-case RPO
  **~2 minutes**.
- Requires Small+ compute and a paid PITR add-on (~$100/mo for 7-day
  retention, higher for 14/28).
- When PITR is on, daily scheduled backups are replaced by the PITR stream
  (docs: running both is unnecessary).

---

## Exclusions and gaps (must not assume coverage)

From Supabase docs + this project's shape:

| Asset | Covered by daily DB backup? | Notes |
|---|---|---|
| Postgres data (corpus, quotes, jobs, auth schema in DB, etc.) | **Yes** (to last daily snapshot) | Physical backup of the project DB |
| Objects in Supabase Storage buckets | **No** (DB holds metadata only) | Docs: restoring DB does not restore deleted Storage objects |
| Custom role passwords | **Not in daily backup download/restore secrets** | Docs: reset passwords after restore if custom roles used (`rhemata_readonly_analysis`, etc.) |
| Railway env / `QUOTE_SELECTION_ENABLED` / service config | **No** | Outside Supabase |
| Vercel frontend deploy / env | **No** | Outside Supabase |
| Local `sources/` PDFs / transcripts | **No** | Off-DB; Drive copy claimed 2026-07-19 — see below |
| GitHub `origin/main` | Separate | Code recoverability ≠ data recoverability |
| In-progress answer jobs / provider usage after last backup | Lost on restore to that day | Async queue state included only as of snapshot time |

---

## What is already proven in-repo (not Supabase project restore)

| Capability | Status | Evidence |
|---|---|---|
| Single-document export → delete → restore (9-table footprint, embeddings) | **Proven 2026-07-24** | `scripts/export_restore_document.py`, `fingerprint_document.py`; Ern Baxter drill + xmin forensic |
| Attachment-bearing single doc (`books` / `feedback` SET NULL path) | **Proven 2026-07-24** | plan-archive #15 |
| 5-document batch export/delete/restore (chunks-only set) | **Proven 2026-07-24** | plan-archive #15 |
| Batch **plus** attachment-bearing docs in one drill | **Still unproven** | Explicit residual in #15 |
| Mid-batch fault injection (partial rollback) | **Still unproven** | Explicit residual in #15 |
| Full **project** restore from Supabase daily backup | **Never tested** | No staging project; no Management API credential in this env |
| Staging Supabase project | **Does not exist** | One production URL/DB only |
| `sources/` + `ingest_queue.xlsx` Google Drive backup | **Claimed done 2026-07-19** | plan-archive #1 |
| Drive **restore** verification | **Still open** | No test-restore recorded; path not re-confirmed this pass |

Record-level scripts remain a **surgical** recovery path for one/few documents.
They are **not** a substitute for project-level disaster recovery.

---

## Owner / RTO / RPO (needs Alex)

| Field | Proposed default | Status |
|---|---|---|
| Owner | Alex (Dashboard + billing) | **Confirmed** (acceptance 2026-08-19) |
| Acceptable RPO | Daily backup (~24h worst case) **without** PITR | **Accepted** by Alex 2026-08-19 |
| Acceptable RTO | Unmeasured; Dashboard restore available; downtime during restore accepted until a timed drill | **Accepted** by Alex 2026-08-19 (no drill required to close inventory) |
| Safest restore scope today | Restore production project to a listed daily physical backup **or** surgical `export_restore_document` for named docs | Documented; project restore **unproven**, explicitly accepted |
| PITR decision | **Leave off** | **Accepted** by Alex 2026-08-19 |

---

## Closure condition for W9 bullet 1 (inventory)

**CLOSED 2026-08-19** by Alex's explicit acceptance of daily-only backups
(~24h RPO), PITR off, and unproven project-level RTO — option (1) below, not a
restore drill.

Formerly: closed when **either**:

1. This inventory is accepted as the authoritative record **and** Alex explicitly
   accepts current RPO (~24h) / unproven RTO / PITR-off, **or**
2. A project-level restore is proven (ideally on a staging clone) and RTO is
   measured.

W9's second checkbox (named web-article batch) stays blocked on **W5–W6** and
is out of scope for this parallel pass.

---

## Parallel-track note (2026-08-19)

Taken while Claude owns QuoteRail design polish. No frontend conflict. No DB
writes. No PLAN.md mutation in this file write — update PLAN/status at session
close if Alex accepts.
