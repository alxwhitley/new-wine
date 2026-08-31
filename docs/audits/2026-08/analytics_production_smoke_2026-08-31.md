# Search analytics — production verification smoke

**Date:** 2026-08-31. **Session type:** attended, Alex at the keyboard.
**Goal:** establish whether search analytics genuinely record and process in
production, end to end.

This is a verification record, not a build record. Nothing in Phase A was
fixed, changed, or granted. The `rhemata_readonly_analysis` role's missing
grants on PII/user tables were explicitly out of scope and were not touched;
Phase A did not need them (see "Access used" below).

---

## Phase A — read-only mapping

### A1. The recording path

One writer, one call site.

| Item | Finding |
|---|---|
| Endpoint | `POST /async-chat/submit` (`backend/app/routers/async_chat.py:155`) |
| Writer | `create_occurrence()` (`backend/app/services/search_analytics/occurrences.py:45`) |
| Table written | `search_occurrences` (one row per accepted submission) |
| Moment in the cycle | **After** `jobs.enqueue()` returns — it needs a real `job_id` — and **before** the HTTP response (`async_chat.py:215-248`). Not in the worker, not post-answer. |
| Precondition | Authenticated **and** current-version consent. `if user_id:` then `consent_status["acknowledged"] and not consent_status["needs_acknowledgment"]`. |
| Guests | Not monitored at all. No row, no error — by design. |
| Fail-open or fail-closed | **Fail-closed.** `OccurrenceWriteFailedError` → `HTTPException(503, "analytics_unavailable")` (`async_chat.py:244-248`). A consented account whose occurrence cannot be durably written **does not get an answer**. |
| Idempotency | `INSERT ... ON CONFLICT (submission_id) DO NOTHING`, falling back to `SELECT`. Two submissions collapsed onto one job by single-flight still produce two occurrence rows, because `submission_id` — not `job_id` — is the occurrence's identity. |
| Content stored | `question_fingerprint` only (SHA-256 of `subject_key:normalized_question`). No account id, no conversation id, no answer text, no raw question. `subject_key` is HMAC-SHA256(secret, user_id) — one-way. |

Second, separate writer: `origin='admin_retest'` rows, written only by the
admin retest endpoint calling `create_occurrence()` directly. `origin` is never
client-suppliable on `/submit`.

Frontend is wired: `frontend/lib/api.ts:346` mints a `crypto.randomUUID()`
`submission_id` per submission and sends it; `frontend/components/rhemata/
consent-gate.tsx` is mounted at `frontend/app/page.tsx:651` and blocks an
authenticated user until they acknowledge.

### A2. The two scheduled services

Verified against Railway (project `dependable-enthusiasm`,
`3f61b055-a1ba-4a79-9a49-f64fe97132a7`, environment `production`), not from
memory. Both names Alex recalled are correct.

| Service | Service ID | Cron | Start command | Root | Builder |
|---|---|---|---|---|---|
| `search-analytics-finalizer` | `edc80e98-20dd-4f12-a0f2-847a965a190d` | `*/5 * * * *` | `/opt/venv/bin/python scripts/search_analytics_finalizer.py` | `/` | NIXPACKS |
| `search-analytics-retention` | `27e71854-22dd-4d51-944e-6a6a8cc1ef5a` | `0 6 * * *` | `/opt/venv/bin/python scripts/search_analytics_retention.py` | `/` | NIXPACKS |

Both are deployed at commit `9f261a9c`, deployment status `SUCCESS`, created
2026-08-31T14:08:06Z — the same commit and timestamp as the `rhemata` and
`answer-worker` services. `5b98e0a` (the last analytics commit) is an ancestor
of `HEAD`, so the deployed image contains the full analytics code.

**What the finalizer actually does** (`backend/app/services/search_analytics/
finalizer.py`): selects `DISTINCT job_id` where the occurrence is `pending` and
the `answer_jobs` row is `done`; classifies each distinct job **once** via Groq
`openai/gpt-oss-120b` against the closed `VALID_TAGS` taxonomy (unknown label or
confidence < 0.70 → forced to `"Unclassified"`); fans the result out to every
occurrence sharing that job; stamps `primary_topic`, `outcome`,
`classification_status='classified'`, classifier provenance, `finalized_at`. It
reads only `answer_jobs.status/outcome/question` and only by `SELECT` — never
answer text, citations, or verified references. A `no_material` + `origin='user'`
occurrence additionally creates one `search_gap_details` row holding the
**redacted** question only. An `admin_retest` occurrence updates an existing
gap's `retest_outcome` instead of creating a second gap.

**What the retention job actually does** (`retention.py:13`): a single UPDATE —
`redacted_question = NULL`, `purged_at = now()` — on `search_gap_details` rows
`WHERE status='resolved' AND text_purge_at <= now() AND redacted_question IS
NOT NULL`. It deletes **wording only**. Row, counts, `resolved_at`, and status
are retained forever. Idempotent by construction: the `IS NOT NULL` predicate
excludes already-purged rows. It cannot touch an open gap, and it cannot delete
a row.

**Live proof both cron services execute** — deployment logs, not inference:

```
finalizer (deployment b372b5a1-…):
  2026-08-31T14:10:07Z Starting Container
  2026-08-31T14:10:08Z {'jobs_classified': 0, 'occurrences_finalized': 0, 'gaps_created': 0, 'gaps_updated': 0, 'failed': 0}
  2026-08-31T14:15:07Z Starting Container
  2026-08-31T14:15:10Z {'jobs_classified': 0, …}
  2026-08-31T14:20:19Z Starting Container
  2026-08-31T14:20:21Z {'jobs_classified': 0, …}
  2026-08-31T14:25:07Z Starting Container
  2026-08-31T14:25:13Z {'jobs_classified': 0, …}

retention (deployment e841faa8-… / prior REMOVED deployments):
  2026-08-31T06:02:11Z Starting Container
  2026-08-31T06:02:14Z {'purged': 0}
  2026-08-30T06:04:42Z Starting Container
  2026-08-30T06:04:43Z {'purged': 0}
```

Both connect to the database, run their pass, print a real result, and exit 0.
The schedules fire on time (finalizer at :10/:15/:20/:25; retention ~06:02 UTC
daily). This is confirmed execution, not confirmed *work* — every observed run
found nothing to do.

Required environment variables are present on the services that need them
(names only, values not read): `rhemata` has `ANALYTICS_HMAC_SECRET_V1` and
`SUPABASE_DB_URL`; `search-analytics-finalizer` has `GROQ_API_KEY` and
`SUPABASE_DB_URL`; `search-analytics-retention` has `SUPABASE_URL` and
`SUPABASE_SERVICE_KEY`. A missing `ANALYTICS_HMAC_SECRET_V1` on `rhemata` would
have 503'd every submission from the consented account —
`subject_key.MissingHmacSecretError` fails loudly by design — so its presence
was checked before any live search was contemplated.

### A3. Live database state (read-only)

Migration 093's three tables all exist (`to_regclass` non-null for
`analytics_consent`, `search_occurrences`, `search_gap_details`).

```
analytics_consent      1 row, active (withdrawn_at IS NULL)
                       policy_version v1, subject_key_version 1
                       acknowledged_at 2026-08-29 16:24:20 UTC
                       account: alexwhitleyy@gmail.com (4ba2f9ce-…)
                       retired_subject_keys: []

search_occurrences     0 rows.  min/max created_at: NULL
                       status distribution: no rows to distribute

search_gap_details     0 rows

async_answer_config    serving_enabled = true, paused = false

answer_jobs            44 rows all-time
                       first 2026-08-06 12:48:11 UTC
                       last  2026-08-28 18:39:26 UTC
                       jobs created since the consent row: 0
```

`GET https://rhemata-production.up.railway.app/async-chat/mode` → `200
{"async_enabled":true}`.

### A4. Phase A verdict

**The data does not show the pipeline working, and it does not show it broken.
It shows the pipeline has never had an opportunity to run.**

The reasoning is arithmetic, not inference. The only account with
current-version consent acknowledged it at 2026-08-29 16:24 UTC. The most
recent `answer_jobs` row in the entire database is 2026-08-28 18:39 UTC —
**before** that. Zero jobs have been created since consent existed. Every one
of the 44 historical jobs predates the consent row, and the recording path
writes nothing for an account without current consent. So zero occurrences is
the *expected* count given the traffic, and carries no information either way
about whether `create_occurrence()` works against the live schema.

Everything that can be verified without traffic, verifies:

- schema applied, all three tables present with their constraints;
- the write path deployed at the current commit on the live web service;
- the HMAC secret the write path depends on is configured on that service;
- both cron services deployed, scheduled correctly, and observably executing
  on time against the live database without error;
- the consent gate and `submission_id` generation shipped on the frontend;
- serving enabled.

What remains genuinely unverified is the single thing no amount of reading
settles: whether a real submission from a consented account actually lands a
row, and whether the finalizer then classifies it. That is exactly Phase B.

Worth stating plainly because it raises the stakes: this path is **fail-closed**
against a live user. If occurrence writing is broken for the consented account,
that account cannot get answers at all — it receives `503
analytics_unavailable`, not a degraded answer. So "does recording work" is not
only an analytics question; on this account it is an availability question.

### Access used

Read-only throughout. Live database reads used the service `SUPABASE_DB_URL`
connection with `conn.set_session(readonly=True)`; every statement was a
`SELECT`. Railway facts came from the read-only GraphQL queries `project`,
`deployments`, and `deploymentLogs`, plus `railway service list` and `railway
variables --kv` (variable **names** only). No grant was added to
`rhemata_readonly_analysis`; nothing about that deferred item was touched.

---

## Phase B — live smoke

Alex gave the go-ahead after the Phase A report and chose to submit through
the browser himself, signed in as `alexwhitleyy@gmail.com` — the truest
available user path (real browser, real JWT, real consent state), and the only
account that records anything. He also chose to include a question aimed at
`no_material` so the gap-creation and redaction half of the finalizer would be
exercised rather than left untested.

### B1. What was submitted

| # | Exact query string | Submitted (UTC) | Job id | Job outcome |
|---|---|---|---|---|
| 1 | `What does it mean to walk in the fear of the Lord day by day?` | 14:32:18 | `f5f46c48-cb3a-49dd-b60b-777655628edc` | `answered` |
| 2 | `In revelation 2 what is the teaching of the nicolaitans?` | 14:33:41 | `26fcc2e6-5127-40df-80b4-b3039585a201` | `no_material` |
| 3 | `What does it mean to walk in the fear of the Lord day by day?` | 14:34:52 | `e77c0eaa-1539-4278-a061-4a14f35157e7` | `answered` |

Question 2 was chosen because it is the one question in the entire job history
that had previously produced `no_material` (2026-08-21). It did so again,
despite the corpus having grown by 63 CLF sermons since.

Three jobs, not two — see B3.

### B2. Occurrence rows landed

Verified by a fresh read-only connection against `SUPABASE_DB_URL`, never from
any submitting code's return value. `search_occurrences` went from 0 rows (its
state for the whole of its existence, Phase A) to exactly 2.

```
id            3b27f818-d289-4879-b546-165eaf1e633c
submission_id afd4bcd8-f717-48f1-b391-7b719a858f23
job_id        26fcc2e6-…  (nicolaitans)
origin        user          subject_key_version 1
created_at    2026-08-31 14:33:42.625579 UTC

id            735d0d6b-6590-4f4a-8b84-235f7240ac29
submission_id e600658f-ba41-4386-a61d-9c459194eeba
job_id        e77c0eaa-…  (fear of the Lord, 2nd submission)
origin        user          subject_key_version 1
created_at    2026-08-31 14:34:53.828522 UTC
```

Both carry `origin='user'`, both carry a `subject_key` that compares equal to
the consent row's current key (checked by SQL join, not by eye), and the two
carry distinct `question_fingerprint` values — 2 occurrences, 2 distinct
fingerprints, consistent with two genuinely different questions. No account id,
conversation id, raw question, or answer text appears in either row.

### B3. The third job — an unplanned proof of the guest branch

Job 1 (14:32:18) produced **no** occurrence row. That was not a defect, and the
explanation is evidential rather than inferred:

- `guest_sessions.last_seen = 2026-08-31 14:32:16 UTC` — a guest session was
  metered two seconds before job 1 was created;
- `user_usage.query_count = 2` for the consented account, week starting
  2026-08-31 — exactly two authenticated searches, not three;
- only two `conversations` rows were persisted (14:34:04 nicolaitans, 14:35:30
  fear), both owned by `4ba2f9ce-…`. Job 1 persisted no conversation, which is
  what a guest read produces.

So the sequence was: one **guest** search, then sign-in, then two authenticated
searches. The guest search correctly produced no occurrence and no history —
the "a guest is simply not monitored" branch of `async_chat.py:215`, exercised
live and confirmed by three independent signals. This was not planned, and it
is worth more than a planned test of the same branch would have been.

### B4. Finalization

Confirmed twice over: by fresh independent database read, and by the
finalizer's own container logs.

```
14:35:03Z Starting Container
14:35:07Z {'jobs_classified': 1, 'occurrences_finalized': 1, 'gaps_created': 1, 'gaps_updated': 0, 'failed': 0}
14:40:07Z Starting Container
14:40:18Z {'jobs_classified': 1, 'occurrences_finalized': 1, 'gaps_created': 0, 'gaps_updated': 0, 'failed': 0}
```

The 14:35 tick took the nicolaitans occurrence; the fear-of-the-Lord occurrence
was still `pending` at that moment because its job had not yet reached
`status='done'` (submitted 14:34:52, the tick ran at 14:35:03). The 14:40 tick
took it. That is the intended `WHERE o.classification_status='pending' AND
j.status='done'` behaviour working as designed — a job mid-generation is
skipped and retried next pass, not failed.

Final state of both rows:

| Occurrence | topic | outcome | confidence | model | finalized_at |
|---|---|---|---|---|---|
| `3b27f818` (nicolaitans) | `Biblical Exposition` | `no_material` | 0.850 | `openai/gpt-oss-120b` | 14:35:05 |
| `735d0d6b` (fear of the Lord) | `Fear of the Lord` | `answered` | 0.990 | `openai/gpt-oss-120b` | 14:40:09 |

Both `classification_status='classified'`. Both stamped
`classifier_version='search_topic_v1'` and
`classifier_prompt_version='search_topic_v1'`. Both topics were checked against
the live closed taxonomy: `'Biblical Exposition' in VALID_TAGS → True`,
`'Fear of the Lord' in VALID_TAGS → True` (258 tags). Neither fell through to
the `Unclassified` sentinel — which is deliberately *not* a member of
`VALID_TAGS`, so a fall-through would have been unmistakable.

### B5. Gap creation and redaction

The `no_material` occurrence created exactly one gap row:

```
id                 aaa58814-dd50-42aa-94e1-0eff2b65885a
occurrence_id      3b27f818-…
redacted_question  "In revelation 2 what is the teaching of the nicolaitans?"
redaction_status   redacted        redaction_version v1
status             open
resolved_at NULL   text_purge_at NULL   purged_at NULL
```

The redacted text is identical to the original here because the deterministic
redactor found nothing personal to remove in this question — the correct
outcome for a purely doctrinal question, not a redaction failure
(`redaction_status='redacted'`, not `'redaction_failed'`). This does not
demonstrate that redaction removes personal detail when personal detail is
present; that path remains untested, and testing it would mean deliberately
submitting a question containing personal information, which was not done.

### B6. Retention job — understood, not run

Not executed against production, per the instruction. Read and traced instead.

The purge predicate is `status='resolved' AND text_purge_at <= now() AND
redacted_question IS NOT NULL`. Its effect is a single UPDATE setting
`redacted_question = NULL, purged_at = now()`. It deletes **wording only** — never
a row, never a count, never `resolved_at`. It cannot touch an open gap, because
an open gap fails the first predicate.

`text_purge_at` is set in exactly one place: `gaps.resolve_gap()`
(`backend/app/services/search_analytics/gaps.py:106`), as `now() +
GAP_TEXT_RETENTION_DAYS` where that constant is `30`. `resolve_gap()` itself
refuses unless the gap's linked retest has already succeeded — it raises
`GapNotRetestedError` when `retest_outcome` is missing or still `no_material`.
Its only caller is `POST /admin/analytics/…/resolve`, `require_admin_role`-gated.

So the full lifecycle is coherent and the 30-day promise in the consent copy is
actually implementable: gap opens → admin retests → finalizer stamps
`retest_outcome` → admin resolves (only if the retest succeeded) → `text_purge_at`
set 30 days out → the daily 06:00 UTC job nulls the wording once that passes.

**What it would delete if it ran right now: nothing.** Confirmed by running the
job's own predicate as a read-only `SELECT count(*)` — `0` rows match. The one
gap in the table is `open` with `text_purge_at IS NULL`, so it is outside the
WHERE clause entirely. Its wording is retained until someone resolves it, which
is the designed behaviour.

### B7. Cleanup — deliberately not performed

The smoke rows are perfectly distinguishable (two occurrence ids, one gap id,
three job ids, two conversation ids, all recorded above). They were still left
in place, and this is a recommendation rather than a blocked action:

- **They are not test rows.** They are genuine searches by a real consented
  account through the real user path. Deleting them would be deleting
  production analytics data, not cleaning up after a test harness.
- **The gap is a true gap.** The corpus really does lack material on the
  Nicolaitans. That row is the corpus-gap dashboard's first legitimate input,
  and it is the kind of finding the feature exists to surface.
- **They are the only evidence the pipeline works.** Deleting them returns the
  tables to the indistinguishable-from-broken empty state Phase A found.
- The two conversations are real entries in Alex's own chat history; removing
  them would touch real user data.

If they should nonetheless be removed, the sanctioned mechanism already exists
and needs no new code: `consent.withdraw()` deletes every occurrence written
under any subject key the account has held, and `search_gap_details` cascades
via `ON DELETE CASCADE`. That is an attended production write and Alex's call —
it was not performed, and no delete of any kind was executed in this session.

### B8. Phase B verdict

**Search analytics genuinely record and process in production, end to end.**
Every stage was confirmed by fresh independent read rather than by any
component's self-report:

- occurrence written at submit time, for a consented authenticated account ✅
- guest submission correctly not monitored ✅ (unplanned, three-signal proof)
- one occurrence per submission, correct `origin`, correct subject key,
  no personal content stored ✅
- finalizer picks up only `pending` occurrences on `done` jobs, on schedule ✅
- classification against the closed taxonomy, real model, real confidence,
  provenance stamped ✅
- `no_material` → exactly one gap row with redacted wording ✅
- retention job traced end to end; would delete nothing today ✅

Cost: three answer generations, ~$0.12 at the measured median.

### What remains unverified

Stated plainly rather than implied by omission:

1. **Redaction of genuinely personal wording.** The one gap produced had
   nothing personal in it, so the redactor's removal behaviour is untested
   live. Testing it means deliberately submitting a question containing
   personal information.
2. **The retention purge actually firing.** No resolved gap exists, so the
   daily job has still only ever been observed returning `{'purged': 0}`. It
   cannot be observed doing real work until a gap completes the
   retest-then-resolve cycle and 30 days pass.
3. **The admin retest → resolve cycle.** `gap_for_retest_occurrence()`,
   `retest_outcome` stamping, and `resolve_gap()`'s refusal guard were read but
   not exercised against production.
4. **The fail-closed 503 path.** Never observed firing, which is the desired
   state. Its existence is confirmed by code reading only.
5. **Concurrency.** Two occurrences arrived a minute apart. The
   `ON CONFLICT (submission_id)` idempotency and the two-occurrences-one-job
   single-flight case were not exercised under real simultaneity.

None of these blocks the question this session was asked to answer.

### Adjacent findings — recorded, not acted on

Per the governing boundary, these are recorded and the session was not expanded
to chase them:

- **`no_material` is not reachable by similarity threshold.** `match_chunks`
  (migration 049) takes no threshold argument and `answer_toolbox.py:359` passes
  none, so vector search always returns its top-k. Whatever empties `chunks`
  for the nicolaitans question happens downstream of retrieval. Not diagnosed —
  it was not this session's question, and the behaviour is correct from the
  user's side.
- **Local `backend/app/.env` has no `ANALYTICS_HMAC_SECRET_V1`.** Production has
  it; the local file does not. Anything run locally that reaches
  `derive_subject_key()` will raise `MissingHmacSecretError`. Not a production
  issue.
- **`classifier_version` and `classifier_prompt_version` always hold the same
  value.** `finalizer.py:78-80` assigns `classification.prompt_version` to both.
  `ClassificationResult` also carries a `prompt_fingerprint` that is computed
  but never stored — the fingerprint-over-label discipline Invariant 10
  established for propositions is not carried through here. Cosmetic today;
  it would matter if the classifier prompt is ever revised without bumping the
  label.
