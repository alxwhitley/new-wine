# O5 — Budgets and Hard Stops: Design Spec

**Goal:** close the four O5 exit criteria in PLAN.md without weakening any O1–O4
guarantee, using deterministic, code-grounded gates only — no LLM judgment
anywhere in this layer, consistent with this repo's standing posture (Open
Decision #20's five failed model-judge attempts; the WORK_TYPE label/content
cross-check idiom in `deterministic_gate.py`/`.claude/harness-selftest/README.md`
cases f/g/h).

Grounded in a full code-read gap analysis (2026-08-11, planner-reviewer,
citations below). Nothing here is guessed; every "absent" claim was verified
by grep/read against the real O1–O4 implementation.

## Scope boundary

O5 is repo-only, same as O1–O4: no production DB, no real provider
commissioning, no network access, no deploy. The synthetic adapter
(`invoke.py`'s fixed operator-owned executable) remains the only thing ever
invoked. Real-provider commissioning stays `HUMAN_REQUIRED` regardless of
anything O5 builds — that gate is a separate, harder prerequisite (an
independently proven pre-execution sandbox) and is explicitly out of scope
here, same as O4's own scoping note.

O6 (concurrent multi-packet rehearsal) is explicitly out of scope. O5's
"finish a useful night" driver is **sequential** — one packet at a time via
repeated `run_once` calls — not concurrent.

## What already exists (do not rebuild)

- **Attempt cap** (bullet 1, half): `scheduler.py:_is_eligible`,
  `classify_runtime.py:_finish_attempt`/`requeue_revise`/
  `_resolve_reassignment_cause` all fail-closed on a missing/malformed
  `retry_limit`. This is solid and untouched by O5.
- **Wall-clock/output/result limiter machinery**: `invoke.py`'s
  `timeout_seconds`/`output_limit_bytes`/`result_limit_bytes`/
  `stop_requested` mechanics, process-group termination, and outcome codes
  (`TIMED_OUT`, `OUTPUT_LIMIT_EXCEEDED`, `RESULT_LIMIT_EXCEEDED`) are
  correct — they are simply never called with real values by the
  coordinator, which passes none and runs at the hardcoded 30s/1MiB
  defaults. O5 wires this up; it does not rebuild it.
- **Provider-exhaustion detection**: `provider_evidence.confirm_provider_exhaustion`'s
  four-guard rule is real and rigorous. O5 adds a *response* (backoff, pause),
  not new detection.
- **Backoff gate**: `scheduler.py:_is_eligible` already excludes a packet
  whose `earliest_next_attempt_at > now`. Nothing currently writes that
  field a non-null value. O5 adds the producer, not the gate.
- **Lane-disable plumbing**: `run_once(..., disabled_lanes=...)` already
  filters `available_lanes` and feeds `select_next`/`_is_eligible`. O5 adds
  a caller that derives it from durable state; `run_cli.py` currently
  always passes `None`.
- **Governed-record edits, undeclared-path writes**: already hard-gated
  twice (admission + O4 postflight). O5 does not touch this.
- **O4 destructive-Git/filesystem detection**: already covers staged/
  out-of-allowlist/secret-like/protected-tree changes. O5 does not touch
  this; it is detective (post-hoc, from Git evidence), which is the
  accepted O4 design and stays that way.

## What O5 adds

### 1. Wall-clock + output-size wiring (exit-criteria bullet 1, other half)

`coordinator.py`'s two `invoke_worker(...)` call sites pass
`packet["budgets"]["wall_clock_seconds"]` and
`packet["budgets"]["max_output_bytes"]` through as `timeout_seconds` and
`output_limit_bytes`/`result_limit_bytes`, and a real `stop_requested`
callable. `invoke.py:persist_invocation_outcome` stops hardcoding
`wall_clock_seconds: 0` and `started_at == finished_at`; it records the
actual elapsed wall time from the invocation's own monotonic start/stop.

This does not require widening the enrollment fold — the raw packet body
(`invocation_packet`/`packet_body` in `coordinator.py`) already carries the
full `budgets` object; only the *folded* scheduling state (`pkt`) was
truncated to `retry_limit` alone, and scheduling doesn't need the other
budget fields.

"Every command has a wall-clock limit": scoped to the one command the
coordinator actually runs (the adapter invocation). There is no
packet-declared-command runner in this build (`invoke.py`'s own docstring:
"never executes packet-selected commands") — building one is a
real-provider-commissioning-era concern, not an O5 gap. `verification_commands[].timeout_seconds`
stays a replay-validated, self-reported field, unchanged.

### 2. Deterministic risk class + hard-stop admission gate (bullet 3)

A new required packet field, `risk_class`, enum `{"routine", "hard_stop"}`.
Enforced the same way `WORK_TYPE` is enforced in `deterministic_gate.py`:
the packet's own declaration is cross-checked against content, and a
mismatch — or an absent declaration — fails closed to `hard_stop`, never to
`routine`. This reuses a proven idiom in this exact codebase rather than
inventing a new one.

A deterministic classifier (pure function, no LLM) scans a packet's
`objective`, `writable_paths`, `forbidden_surfaces`, and `context` for
hard-stop indicators:

- path patterns: `migrations/`, `supabase/`, any path outside the repo
  worktree, deployment config paths (`railway.json`, `nixpacks.toml`,
  `.github/workflows/`)
- keyword patterns (case-insensitive, word-boundary): DB-write verbs
  paired with production/live/DB context (`INSERT INTO`, `UPDATE `,
  `DELETE FROM`, `ALTER TABLE`, `migration`, `backfill`, `ingest`),
  deployment terms (`deploy`, `railway up`, `production`), doctrinal/
  licensing terms (`doctrin`, `licens`, `copyright status`, `position
  paper`)
- `network_policy == "allowed"` — always `hard_stop` (no proven sandbox
  exists yet to make outbound network access anything but a hard stop)

If any indicator fires and `risk_class != "hard_stop"`: **enrollment is
refused** (`PacketPreflightError`, same family as existing preflight
errors), not silently downgraded. If `risk_class == "hard_stop"` (whether
self-declared or forced): the packet still enrolls (so it's visible and
trackable) but is enrolled directly into a state that requires human
action before any invocation is possible — never dispatched to a worker
automatically. This reuses the existing `HUMAN_REQUIRED` terminal-ish
state rather than inventing a new one.

This closes the "DB writes, migrations, deployment, doctrinal content,
licensing determinations" gaps the audit found completely ungated. It
does not attempt objective-level scope-creep detection beyond what O4's
file-scope check already does — that remains a known, accepted residual
(same posture as O4's own "cannot detect objective-level scope expansion
within an allowlisted path" note).

`human_stop_conditions` and `network_policy` stay real schema fields but
this task does not wire `human_stop_conditions` (free text, not
deterministically checkable — reusing it as a second signal into the
classifier is out of scope; a future session could fold its keywords in
as an additional signal, not required to close bullet 3 today).

### 3. Bounded backoff, then fallback, then pause (bullet 2)

When `_finish_attempt` resolves a `PROVIDER_EXHAUSTED` classification:

- **First occurrence, fallback available** (existing behavior, unchanged):
  `provider_exhausted_reassignment` → the one-shot Kimi→Sonnet reassignment
  fires exactly as today.
- **Backoff**: any attempt that lands on `attempt_budget_exhausted` or
  `fallback_not_permitted` after a confirmed `PROVIDER_EXHAUSTED` writes a
  deterministic `earliest_next_attempt_at` (a fixed function of attempt
  count — e.g. `min(2**attempts_started, cap) minutes`, no wall-clock
  randomness, reproducible from durable state alone per D0.4) into the
  packet's derived state via the existing fold, instead of leaving it
  `None` forever. This makes the already-built `scheduler.py` gate actually
  fire.
- **Pause**: when a lane has a confirmed `PROVIDER_EXHAUSTED` with no
  further recourse (Sonnet lane itself exhausted, or reassignment already
  used/not permitted), that lane is recorded as disabled for the rest of
  the run. A new pure function derives `disabled_lanes` from the fold
  (mirroring how `reconcile.py`/`cli.py` already derive read-only reports
  from durable state) so a caller never has to track this itself in
  memory. `run_cli.py` (and the new session driver, below) call it before
  every `run_once`.

This is a genuine behavior change to `_finish_attempt`/`_resolve_reassignment_cause`,
so it gets full RED/GREEN coverage against the existing O3-P5 test suite
plus new backoff/pause-specific fixtures — the existing 656+804 tests must
stay green throughout.

### 4. Sequential session driver + queue-wide limits (bullet 4)

A new pure-ish orchestration entry point, `run_session()`, that repeats
`run_once` calls until one of:

- no eligible packet remains (derived from the same fold `select_next`
  already computes — no eligible work is a clean, successful stop, not an
  error)
- `max_packets_per_session` reached (a new required queue-wide limit,
  supplied by the caller — the "queue-wide limits" deliverable)
- `max_session_wall_clock_seconds` elapsed (measured against the fresh
  `now` each iteration provides, not an internal clock)
- every lane is disabled (nothing left this session can make progress —
  a clean stop, distinct from an error)

Each iteration still goes through the single-packet-claim, crash-safe
`run_once` — this task adds a loop around it, not a new claiming
mechanism. Per O3/O4's established isolation, one packet's `QUARANTINE`/
`HUMAN_REQUIRED`/failure never stops the loop; only the four conditions
above do.

Because D0.4 forbids an implicit clock inside pure functions, and
`cli.py`'s existing precedent restricts `datetime.now()`/`uuid` calls to
CLI entry points, `run_session()`'s loop itself takes a `now_factory`
callable (injected, defaults to real UTC time only at the new CLI's
edge) rather than calling `datetime.now()` internally — keeping the same
testability property every other O3/O4 component has (a test can drive it
with fixed, advancing timestamps and assert exact stop conditions).

A new write-CLI, `run_session_cli.py`, mirrors `run_cli.py`'s existing
"this is the one place allowed to call real time" carve-out, adds
`--max-packets` and `--max-wall-clock-seconds`, and prints one
machine-readable session summary (packets processed, stop reason, final
disabled lanes) — the "morning report" bullet 4 implies.

### 5. Bounded provider-evidence excerpt (Grok's verification ask)

`provider_evidence.matched_signal.byte_length` currently has no maximum.
Add one (a small constant, e.g. 4096 bytes — enough to prove a match,
not enough to leak a large payload) enforced in
`provider_evidence.py`'s validator, matching the existing "positive
integer" check's style. This is the one concrete, low-risk fix available
today for "logs contain no ... prompt payloads that should remain
private" — full redaction of captured worker stdout/stderr is explicitly
deferred (same posture as the sandbox prerequisite): the adapter is
synthetic today, so there is no real secret to leak yet, and a redaction
pass against real provider output can't be correctly designed until real
output shapes exist. Record this deferral explicitly in the commissioning
audit, not silently.

## Explicitly not built in O5 (record, don't silently drop)

- Turn counting (no runtime turn-loop concept exists; the adapter is a
  single subprocess, not a multi-turn agent loop yet — this is
  real-provider-commissioning-era work)
- `allowance_limit` enforcement (no consumer exists; without a real
  provider there is nothing to meter against yet)
- `guard_denials` ingestion from `.Codex/hooks/guard_pretooluse.py` into
  the coordinator's authority block (that hook operates on this
  orchestrating session's own tool calls, not on a packet worker
  subprocess's — there is no hook-injection mechanism for a worker
  subprocess yet, and building one is real-provider-sandbox territory)
- Lease-expiry time-based staleness (`claim.py`'s `classify_claim` is
  deliberately identity-based, not clock-based, per O3-P5's "pin worker
  claims to state root identity" decision — not an O5 bug)
- Full redaction of captured stdout/stderr (see above)
- Concurrent multi-packet rehearsal (O6)

## File map

- Modify: `scripts/harness_coordinator/v1/invoke.py` (wall-clock capture fix)
- Modify: `scripts/harness_coordinator/v1/coordinator.py` (wire budgets into
  both `invoke_worker` call sites; add `run_session()`)
- Modify: `scripts/harness_contracts/v1/packet.py` (`risk_class` field +
  validator)
- Modify: `schemas/harness/v1/packet.schema.json` (`risk_class` field)
- Create: `scripts/harness_coordinator/v1/risk_classify.py` (deterministic
  hard-stop content classifier, pure function)
- Modify: `scripts/harness_coordinator/v1/enroll.py` (call the classifier,
  refuse/force-`HUMAN_REQUIRED` on mismatch)
- Modify: `scripts/harness_coordinator/v1/classify_runtime.py` (backoff
  computation, pause/disabled-lane derivation)
- Create: `scripts/harness_coordinator/v1/run_session_cli.py`
- Modify: `scripts/harness_contracts/v1/provider_evidence.py` (excerpt cap)
- Create/modify `.claude/harness-selftest/test_o5_*.py` fixtures per task

## Plan self-review checklist

- Every O5 exit-criteria bullet maps to a numbered section above.
- Nothing here duplicates an existing O1–O4 mechanism; every section names
  what's reused.
- No LLM judgment call anywhere in the new gates — pure functions over
  packet content and durable state only.
- Real-provider commissioning, O6 concurrency, and turn/allowance
  accounting stay explicitly out of scope, named, not silently dropped.
