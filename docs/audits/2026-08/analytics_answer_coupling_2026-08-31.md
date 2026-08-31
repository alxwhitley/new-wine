# Fail-closed analytics → answer coupling

**Date:** 2026-08-31. **Type:** read-only investigation. **Scope:** define the
problem only — no fix was designed, chosen, or implemented, per Alex's
instruction. Every claim below is from reading the deployed code at commit
`1c02492`; nothing was executed against production for this document.

**The finding, as stated going in:** the analytics recording path is
fail-closed, so for a consented signed-in account, analytics availability is
answer availability. That framing is right in substance and **too narrow in
one respect** — see (c). The coupling reaches every signed-in user, not only
consented ones.

---

## (a) Where the coupling lives

**One endpoint, three separate blocking calls — not one.** All of it is in
`backend/app/routers/async_chat.py`'s `POST /async-chat/submit`, lines
215–248. The worker (`scripts/answer_worker.py`), the whole
`async_answers/` service package, and the `/result` delivery path contain no
analytics call at all — confirmed by grep, they are analytics-free. So the
coupling is confined to submission, and nothing about generation or delivery
depends on analytics.

Order of operations inside `/submit`, with the failure consequence of each:

| # | Line | Call | Transport | Guarded? | On failure |
|---|---|---|---|---|---|
| — | 172 | serving switch | direct PG | n/a | 503 `async_serving_disabled` |
| — | 179 | `enforce_query_limit` | PostgREST | deliberate | 400/429/503 — **quota already incremented past here** |
| — | 203 | `jobs.enqueue` | direct PG | n/a | 503 `queue_full` — **job now exists past here** |
| 1 | 216 | `consent_service.get_consent_status` | PostgREST | **no** | uncaught → **500** |
| 2 | 223 | `consent_service.get_or_rotate_subject_key` | PostgREST | **no** | uncaught → **500** |
| 3 | 243 | `create_occurrence` | direct PG | yes, narrowly | `OccurrenceWriteFailedError` → **503** `analytics_unavailable` |

Two things follow that are easy to miss:

**The documented fail-closed 503 is only branch 3.** Branches 1 and 2 have no
`except` around them at all. They are not "fail-closed" in any designed sense —
they are simply unhandled, and produce FastAPI's generic 500. That is strictly
worse than the 503: there is no detail string, no contract, and the client has
no branch for it.

**All three run *after* the job is already enqueued and the quota already
spent.** By line 215 the submission has been metered (line 179) and a real
`answer_jobs` row exists (line 203). Nothing rolls either back. So an analytics
failure does not prevent work — it prevents *delivery of the job id*. The
worker still picks the job up, still calls the model, still completes it. The
user's client never received a `job_id`, so it never polls `/result`. The
answer is generated, paid for, and thrown away.

I checked whether the most likely failure — the database being unreachable —
escapes branch 3's narrow `except` via `Db()` construction sitting outside the
try block. **It does not.** `Db.__init__` only sets `self._conn = None`
(`async_answers/db.py:73`); the connection opens lazily on first `.conn`
access, which happens inside `db.run()` inside `create_occurrence`'s try, and
`create_occurrence` re-raises everything as `OccurrenceWriteFailedError`. So
connection failure correctly produces the designed 503. Recorded because it
was a plausible-looking defect that turned out not to be real.

---

## (b) What actually triggers it

Distinguishing the classes asked about, and separating what takes the answer
down from what is already tolerated.

### Takes the answer down today

**Analytics/consent table unavailable (PostgREST leg) → 500.** Branches 1 and 2
both read `analytics_consent` through supabase-py. Any transport or API error —
PostgREST down, network blip, RLS/permission change, Supabase maintenance —
propagates uncaught. Note branch 2 re-reads the *same row* branch 1 just read,
so this is two independent round-trips against one table, doubling the exposure
window for no functional gain.

**`search_occurrences` unavailable / write rejected (direct-PG leg) → 503.**
Branch 3: connection failure, pooler drop (retried once by `Db.run`, then
re-raised), constraint violation, permission error. This is the designed path
and it behaves as designed.

**Consent row disappearing mid-request → 500.** `get_or_rotate_subject_key`
raises a bare `ValueError("no consent row for user_id=...")` when the row is
gone. Branch 1 confirmed consent existed moments earlier, so this needs a
withdrawal landing between two reads in the same request. Narrow, but it is a
real uncaught path, and it is reachable by an ordinary user action rather than
an outage.

**A hung — as opposed to failing — dependency.** No timeout is configured
anywhere on this path: no `statement_timeout`, no `connect_timeout`, and
nothing overriding the client defaults (grep found none in
`async_answers/db.py` or `db/supabase.py`). A database or PostgREST that
accepts the connection and never answers holds the request open rather than
failing it. That degrades as a client-side hang, not as a clean error, and no
branch above catches it.

### Already tolerated — no answer impact

**Classification / taxonomy failure.** Runs in the finalizer, not the request.
`classify_topic` raising `ClassificationFailedError` is caught in
`finalize_ready_jobs` (`finalizer.py:66-68`), counted as `failed`, and skipped
for retry next pass. A model label outside `VALID_TAGS`, or confidence below
0.70, is coerced to `"Unclassified"` rather than raising. Groq being down
delays classification indefinitely; it never touches an answer.

**Redaction failure.** `redact_question` wraps its whole body and returns
`RedactionResult(text=None, status="redaction_failed")` on any exception
(`redaction.py:70-78`) — it cannot raise. It also fails *safe*: on failure it
stores no text at all rather than a half-redacted string. Runs in the
finalizer regardless. No answer impact.

**Provenance.** The classifier's version/model/confidence stamping is plain
assignment onto an already-fetched row inside the finalizer. Not on the
request path.

**HMAC secret missing.** Worth stating precisely because it looks like an
answer-path risk and currently is not. `_rotate_if_stale` returns early when
`row["subject_key_version"] >= CURRENT_SUBJECT_KEY_VERSION`, and today every
row is version 1 with the constant at 1 — so `derive_subject_key` is never
called from `/submit`, and `MissingHmacSecretError` cannot fire there.
It fires from `acknowledge()` on the `PUT /analytics/consent` route instead.
**This becomes an answer-path failure the moment `CURRENT_SUBJECT_KEY_VERSION`
is bumped**, because every consented user's next submission would then attempt
a derivation inside unguarded branch 2. A key rotation is currently a
latent outage.

---

## (c) Who is exposed

This is where the premise needs correcting.

| Population | Branch 1 (consent read) | Branch 2 (subject key) | Branch 3 (occurrence write) |
|---|---|---|---|
| Guest (no JWT) | not reached | not reached | not reached |
| Signed in, **never consented** | **exposed** | not reached | not reached |
| Signed in, consent **withdrawn** | **exposed** | not reached | not reached |
| Signed in, **consented** | **exposed** | **exposed** | **exposed** |

Guests are completely immune — `if user_id:` (line 215) gates the entire block,
and `get_optional_user` returns `None` for a missing *or invalid* JWT rather
than raising, so even a malformed token routes a caller down the guest path.

But the consent *check itself* is unprotected and runs for **every** signed-in
user before anyone knows whether they consented. So a `analytics_consent` read
failure takes answers away from all signed-in users, including those who never
opted in and those who explicitly withdrew. A user who withdrew consent
specifically to stop being tracked can still lose their answers to an outage of
the tracking subsystem. That is the sharpest form of the problem and it is not
what the original framing describes.

Scale check, live as of 2026-08-31: 5 accounts exist, 1 consented. So today the
exposed population is small — but the ratio inverts at beta, when signed-in
users are the norm and the consent gate is mandatory at signup.

---

## (d) Is any of it load-bearing? — the key question

Short answer: **the protections are real, but they are achieved by not
*recording*, not by not *answering*. The current code conflates those two.**

Taking each in turn.

**Branch 1 — genuinely load-bearing, in one direction only.** If a consent-read
failure were "tolerated" by assuming consent and recording anyway, that is a
straightforward consent violation: recording the searches of someone who never
opted in, or who withdrew. That must never happen. But the protective action
required is *skip the occurrence*, which is fully compatible with serving the
answer. Blocking the answer protects nobody. **The direction matters and must
be preserved in any change: unknown consent must resolve to "not consented,"
never to "consented."**

**Branch 2 — genuinely load-bearing, and the most subtle of the three.** Two
distinct commitments hang off it:

- The schema requires `origin='user' → subject_key NOT NULL` (migration 093's
  CHECK). So there is no such thing as a degraded user occurrence. Any
  "tolerate the failure" that invented a fallback or placeholder key would
  break the irreversibility guarantee the subject key exists to provide.
- More important: the rotation catch-up records the *old* key in
  `retired_subject_keys` before adopting a new one, precisely so
  `consent.withdraw()` can still find and delete rows written under it
  (`consent.py:63-91`, the 2026-08-27 privacy review's Finding 2). If a
  rotation half-completed — new key derived, the `analytics_consent` UPDATE
  failing — occurrences would be written under a key the consent row does not
  know about, and **withdrawal would silently fail to delete them**. That is a
  direct breach of the stated deletion promise.

So branch 2 must never write an occurrence it cannot guarantee is deletable.
Again: the required protection is *don't record*, not *don't answer*.

**Branch 3 — not load-bearing for anything. This is the incidental one.** Its
own log line states the intent: "refusing rather than serving an unmonitored
search." That protects **analytics completeness**, which is a product-quality
goal, not a privacy, consent, or safety goal. Nothing leaks when a write fails;
the failure is a failure to *write*. Checked against the actual promise made to
users — the consent copy (`consent.py:21-29`) says Rhemata *tracks* the topics
you search and that gap wording may be stored. That is a **disclosure that
collection happens**, not a guarantee to the user that every search is
recorded. A search that goes unrecorded harms Alex's dashboard, not the user.

Contrast with the fail-closed decision one line up that *is* correct:
`enforce_query_limit` (line 179) is deliberately fail-closed because failing
open would let a caller exceed the weekly quota — a real abuse and cost
control, where the failure mode is the user getting *more* than they should.
Analytics has no equivalent: failing open costs a dashboard row.

**Bottom line for (d):** two of the three branches are protecting something
real and must keep failing closed *with respect to recording*. None of the
three requires withholding an answer. The coupling exists because "skip the
write" and "reject the request" were never separated.

---

## (e) Blast radius today

**Per failed attempt**, for an affected user:

- the weekly quota is incremented and not refunded (metering at line 179 runs
  first, and nothing compensates) — against a 50/week limit;
- a real `answer_jobs` row exists and is completed by the worker at full model
  cost (~$0.039 median, measured 2026-08-03) and delivered to nobody;
- the user sees an error and no answer.

**What the user is actually told is wrong.** Tracing the client: a 503 with
detail `analytics_unavailable` does not match the `async_serving_disabled`
branch in `frontend/lib/api.ts:379-389`, so it falls through to `throw new
Error("queue_full")`. A 500 falls to `throw new Error("Chat request failed")`.
Neither string is handled specifically in `frontend/hooks/useChat.ts:227-251`,
so both land in the generic branch: **"Something went wrong. Please try
again."** So an analytics outage is reported to the user as a transient glitch,
and internally mislabels itself as a full queue.

**And the UI actively invites the retry that multiplies the cost.** That same
branch calls `withoutFailedTurn(prev)`, stripping the failed turn "so a retry
can resubmit cleanly in place." Single-flight only collapses onto jobs with
`status IN ('queued','running')` (`jobs.py:120-124`), and reuse is off
(`reuse_ttl_seconds = 0`), so once the first job finishes — 30–60s — each
retry creates a **new** job. A user retrying a few times during a sustained
outage burns several generations and several quota units, receives nothing, and
is told each time to try again.

**Would Alex find out? No.** Every signal is absent or ambiguous:

- **No error monitoring exists.** Grep found no Sentry, Rollbar, Datadog,
  OpenTelemetry, or PagerDuty integration anywhere in `backend/`, `frontend/`,
  or `scripts/`.
- **The healthcheck cannot see it.** `backend/railway.toml` sets
  `healthcheckPath = "/"`. The app stays up and healthy while `/submit` returns
  500s to every signed-in user.
- **Logs exist for one branch only and nobody reads them.** Branch 3 calls
  `logger.exception(...)` into Railway logs; branches 1 and 2 produce a default
  FastAPI traceback. There is no alert on either.
- **The analytics feature cannot detect its own outage.** This is the sharp
  one. The failure signature is "no occurrence rows appear," which is *byte for
  byte identical* to "no traffic." The finalizer would keep logging
  `{'jobs_classified': 0, ...}` — exactly what it logged every five minutes
  through the whole of 2026-08-31 while healthy. That ambiguity is not
  hypothetical: it is precisely what Phase A of the smoke test ran into on
  2026-08-31, where an empty table took a live submission to disambiguate.

**So the first signal is a user reporting that they cannot get answers** — and
because the on-screen copy says "Something went wrong. Please try again," a
user is more likely to retry, give up, and say nothing than to report it.

---

## Remediation options

Listed with what each gives up. **Not ranked, and none chosen** — that decision
is Alex's and is explicitly out of scope for this session. They are not mutually
exclusive; several compose.

### Option 1 — Decouple: skip the occurrence, serve the answer

Wrap all three branches, catch broadly, log, and continue. Consent-unknown
resolves to not-consented, per (d).

- **Gives up:** guaranteed analytics completeness. The dashboard silently
  under-counts during any outage, and — unless paired with monitoring — nothing
  says which searches are missing or how many. Given (e)'s point that missing
  rows are indistinguishable from no traffic, this option without Option 5
  makes the data quietly untrustworthy rather than visibly incomplete.
- **Keeps:** every protection in (d), since all of them are satisfied by not
  recording.

### Option 2 — Atomicity: write the occurrence in the job's own transaction

Move consent/subject-key resolution before `enqueue`, and insert the occurrence
in the same direct-PG transaction as the `answer_jobs` row, so either both land
or neither does.

- **Gives up:** the current clean layering, and a meaningful amount of
  restructuring in a path that is presently simple and works. Does not help
  branches 1–2, which are PostgREST reads that cannot join that transaction —
  their failure still has to be decided separately.
- **Keeps:** completeness *and* removes the "answered but unrecorded" and
  "enqueued but undelivered" states entirely — a failure becomes an honest
  "submission not accepted," with nothing generated and nothing charged.

### Option 3 — Defer: record the occurrence outside the request

Persist the intent with the job and let the worker (or the finalizer) write the
occurrence, or use a durable outbox.

- **Gives up:** immediacy, and it adds a new moving part with its own failure
  mode and its own backlog to monitor. Consent must be evaluated at submission
  time and carried, or a user who withdraws between submission and write gets
  recorded anyway — a consent regression if done carelessly.
- **Keeps:** completeness with no request-path coupling at all.

### Option 4 — Cache the consent read

Short-TTL cache of consent status so a PostgREST blip cannot take down every
signed-in user, and so branch 2's redundant second read of the same row
disappears.

- **Gives up:** withdrawal freshness. A user who withdraws consent could
  continue being recorded for up to the TTL. That is a real, user-visible
  privacy cost and would need Alex's explicit acceptance of a specific TTL;
  it is not a free optimization.
- **Note:** collapsing branch 1 and branch 2's duplicate read into one is
  strictly an improvement with no such cost, independent of any caching.

### Option 5 — Leave the behaviour, fix the visibility

Change nothing about fail-closed. Add real error monitoring, alert on
`analytics_unavailable` and on 500s from `/submit`, and give the client an
honest message instead of "queue_full" / "Something went wrong."

- **Gives up:** nothing — but it does not fix the problem. Users still lose
  answers during an analytics outage; Alex just finds out promptly.
- **Note:** the client-message correction is worth doing under any option, and
  the "please try again" copy actively multiplies cost during an outage.

### Option 6 — Compensate on failure

Keep fail-closed, but on failure cancel the enqueued job and refund the
metering increment.

- **Gives up:** little, but adds a compensation path that is itself capable of
  failing partway, and it does not restore the user's answer. Addresses the
  waste in (e), not the outage.

### Cross-cutting, independent of which option is chosen

- Branch 2 becomes a live outage the moment `CURRENT_SUBJECT_KEY_VERSION` is
  bumped (see (b)). Whatever is decided should be in place before any key
  rotation, or the rotation itself becomes the incident.
- No timeout is configured on this path, so a hung dependency hangs the
  request under *every* option above. That is a separate defect from the
  coupling and is not fixed by any of them.

---

## What this document does not do

No fix was designed, prototyped, or applied. No option is recommended. No code,
schema, configuration, or deployed setting was changed, and nothing was run
against production to produce this — every finding is from reading the deployed
source at `1c02492`. The one live-system fact cited (5 accounts, 1 consented)
is carried from the 2026-08-31 smoke audit, not re-queried here.
