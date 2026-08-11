# O5 Budgets and Hard Stops — Design

Date: 2026-08-11
Status: approved conversational design; written-spec review pending
Branch: `codex/o5-budgets-hard-stops`

## Purpose

O5 makes one approved execution plan the finite unit of autonomous work. The
coordinator may finish that plan safely, but it cannot enlarge the plan, loop
indefinitely, silently downgrade model capability, or spend provider allowance
merely because capacity remains.

O5 treats subscriptions as capacity-constrained services, not estimated dollar
budgets. Time, attempts, retries, output, and provider availability remain hard
operational boundaries. Each plan must declare a positive wall-clock safety
ceiling within the schema maximum; the repository supplies no implicit
duration. That ceiling is a backstop and does not define successful completion.

## Non-goals

- Commissioning a real provider or measuring a live subscription allowance.
- Production database or network access.
- Deployment, merging, pushing, or destructive Git/filesystem actions.
- Concurrent multi-packet rehearsal, which remains O6.
- Automatic model qualification based on provider catalog availability.
- Monetary cost estimation for subscription-backed lanes.
- Altering answer generation, retrieval, doctrinal content, or position papers.

## Governing principles

1. The approved plan is the work budget.
2. Durable accounting comes from authenticated coordinator evidence, never
   worker claims or mutable caches.
3. Immediate process-safety limits and graceful run stops are distinct.
4. Fallback preserves capability class and authority; availability never
   authorizes a downgrade.
5. Active work may finish when a graceful stop becomes due, but no subsequent
   packet may be claimed.
6. Any ambiguity in budget, provider, plan, or authority evidence fails closed.

## Authenticated execution plan

Every run binds to one immutable canonical plan artifact before the first
claim. Its identity is a SHA-256 digest over canonical bytes. The plan contains:

- `plan_id`, schema version, and content digest;
- the exact packet IDs and packet digests in scope;
- the dependency graph and deterministic enrollment order;
- each packet's capability class;
- permitted model routes by capability class;
- packet attempt, retry, command-time, turn, and output limits;
- provider backoff policy;
- a run-level wall-clock safety ceiling;
- human-stop categories; and
- terminal accounting requirements.

The coordinator rejects missing, noncanonical, tampered, or internally
inconsistent plans. It rejects enrolled packets outside plan membership and
plan members whose packet digest or dependency declaration differs. A material
change creates a new plan identity; it cannot be represented as a retry or
in-place edit.

The run ends when every plan member is accepted, revised and resting,
quarantined, paused for provider capacity, blocked for human judgment, or
otherwise terminal under the plan. Remaining provider capacity does not permit
new enrollment or discovery.

## Budget layers

### Immediate process safety

These limits terminate the current process group because allowing it to finish
would defeat the safety boundary:

- per-command timeout;
- per-attempt output byte limit;
- explicit operator stop;
- loss of process identity or containment evidence; and
- an existing O4 filesystem/worktree hard failure.

Termination preserves bounded stdout/stderr metadata and process evidence. It
does not reinterpret a safety failure as a graceful plan stop.

### Packet limits

Packet limits are authenticated plan values and cannot exceed constitutional
schema maxima. They include attempts, retries, revision cycles, turns, command
timeouts, and output bytes. Before `ATTEMPT_STARTED`, the coordinator derives
usage from the journal and refuses a claim that would exceed a limit.

The coordinator cross-checks worker-reported usage only as untrusted evidence.
A disagreement is an integrity finding; it cannot increase remaining budget.

### Graceful run limits

The plan-level wall-clock ceiling and authenticated provider-exhaustion signals
are graceful stop conditions. If observed during an active attempt, the
coordinator lets that attempt reach a durable outcome and complete mandatory O4
postflight. It then stops before the next claim. If no attempt is active, the
stop is effective immediately.

The wall-clock ceiling is a backstop against abandoned runs. Plan completion,
not elapsed time, is the normal success condition.

## Capability classes and routing

The initial closed capability vocabulary is:

- `design_judgment`
- `planning_architecture`
- `implementation`
- `independent_review`
- `adversarial_audit`
- `mechanical_check`

Each route entry binds a provider, exact model identifier, minimum reasoning
level where applicable, enabled state, and qualification record. Provider
catalog discovery cannot enable a model or change its class.

Initial policy:

| Capability | Ordered route | Stop behavior |
|---|---|---|
| Design judgment | `claude-fable-5`; `gpt-5.6-sol` at `max` disabled pending Alex's blinded evaluation | Pause for Alex if no enabled model remains |
| Planning/architecture | `claude-fable-5`; `gpt-5.6-sol` at `max` | Pause if both are unavailable |
| Implementation | plan-pinned OpenCode Go coding model selected from the qualified registry; `gpt-5.6-terra`; plan-pinned qualified Claude Sonnet model | Pause if no approved implementation model remains |
| Independent review | `gpt-5.6-sol` at `xhigh` or `max`; `claude-fable-5`; plan-pinned qualified Grok reviewer | Pause rather than use executor-tier judgment |
| Adversarial audit | plan-pinned qualified Grok model; `gpt-5.6-sol`; `claude-fable-5` | Pause if the required audit cannot be performed |
| Mechanical check | deterministic local tooling first; qualified OpenCode Go model or `gpt-5.6-terra` only when interpretation is required | Escalate to a judgment class when judgment becomes material |

OpenCode Go is an authenticated pool of individually qualified model IDs, not
an authorization for every model exposed by its catalog. Newly appearing model
IDs are disabled until a qualification record assigns a capability class.
At plan creation, every registry selector resolves to one exact provider/model
ID and that resolved route is included in the plan digest. Runtime catalog
order, aliases, or later registry changes cannot change an active plan.

The same invocation cannot act as implementer and reviewer. The coordinator
prefers a different model family for independent review and records any
unavoidable loss of family diversity as `HUMAN_REQUIRED`; it does not silently
weaken the review contract.

No fallback changes filesystem, command, network, database, deployment,
content, or scope authority.

## Provider exhaustion and backoff

Provider allowance evidence is accepted only from the existing authenticated
provider-evidence path. Worker prose, stderr text, and guessed reset times are
untrusted.

On confirmed exhaustion:

1. Finish and postflight any active attempt.
2. Persist the provider state and stable reason code.
3. Apply the plan's bounded backoff using an authenticated reset time when one
   exists; otherwise use a finite schedule with an absolute retry count.
4. Before another claim, choose the next enabled, qualified model in the same
   capability class.
5. If none is eligible, pause the affected packet or lane and expose it in
   reconciliation.

Fallback graphs must be acyclic. A model/provider pair already exhausted for
the current plan cannot be selected again until authenticated evidence proves
the allowance window reset. Restarting the coordinator does not reset backoff
or fallback history.

## Human hard stops

The following always stop for Alex regardless of model, remaining time, or
provider availability:

- production database writes or migrations;
- deployment or live configuration changes;
- destructive Git/filesystem actions;
- merge, push, stage, commit, clean, or deletion authority not explicitly in
  the current approved workflow;
- doctrinal, position-paper, or other governed-content changes;
- licensing determinations;
- unapproved network/provider commissioning; and
- material scope expansion or plan replacement.

O5 may report the required action but cannot manufacture approval from prior
unrelated instructions.

## Durable events and reconstruction

O5 adds closed, schema-validated events for:

- plan binding;
- provider availability/exhaustion observation;
- fallback selection;
- bounded backoff scheduling;
- packet/lane pause;
- graceful run stop requested;
- graceful run stop effective; and
- final plan reconciliation.

Events contain stable reason codes and bounded identifiers, not credentials,
prompt bodies, raw provider responses, environment values, or unrestricted
stdout/stderr. Artifacts use canonical bytes, content hashes, collision-safe
publication, and the pinned state-root handle.

On restart, the coordinator folds the authenticated journal to reconstruct plan
membership, attempts, retries, fallback history, backoff, pauses, and pending
graceful stops. Mutable cache state cannot authorize work. Clock regression,
missing reset evidence, contradictory usage, or an event outside the bound plan
produces an integrity finding and prevents a new claim.

Within one process, deadlines use monotonic time. Durable UTC timestamps are
used only with explicit ordering and skew validation. A restart conservatively
honors an already-recorded stop or backoff rather than assuming time remains.

## Stop reason vocabulary

Stable families include:

- `PLAN_IDENTITY_*`
- `PLAN_SCOPE_*`
- `PACKET_BUDGET_*`
- `COMMAND_TIMEOUT`
- `OUTPUT_LIMIT_EXCEEDED`
- `QUEUE_SAFETY_CEILING_REACHED`
- `PROVIDER_ALLOWANCE_*`
- `PROVIDER_BACKOFF_*`
- `MODEL_ROUTE_*`
- `NO_CAPABLE_MODEL_AVAILABLE`
- `HUMAN_AUTHORITY_REQUIRED`
- `BUDGET_EVIDENCE_INVALID`

Unknown reason codes fail schema validation. User-facing details remain
secret-safe and bounded.

## Reconciliation

Final reconciliation reports exact, mutually reconcilable plan totals:

- planned;
- attempted;
- accepted;
- resting in revise;
- quarantined;
- paused for provider capacity;
- blocked for human judgment; and
- never started.

Every plan member appears exactly once in the terminal disposition partition,
and the partition sum equals `planned`. Attempt, retry, fallback, and stop-event
identities are checked independently. A useful partial run can close cleanly
with paused or human-blocked packets, but it cannot claim plan completion.

## Crash and adversarial matrix

Tests inject crashes:

- before and after plan binding;
- before and after `ATTEMPT_STARTED`;
- after observing exhaustion but before recording backoff;
- after a worker exits but before receipt ingestion;
- after receipt ingestion but before O4 postflight;
- after requesting a graceful stop but before it becomes effective;
- during fallback selection; and
- before final reconciliation publication.

Negative tests cover boundary values, booleans masquerading as integers,
tampered plans, forged/stale provider evidence, fallback cycles, provider reset
replay, output floods, hung process groups, clock regression, model catalog
drift, cross-class fallback, executor-as-reviewer reuse, one-extra-claim races,
and plan-membership expansion.

Commissioning uses disposable repositories, synthetic adapters, and fake
clocks only. It proves that an active attempt may finish after a graceful stop
condition, no later packet is claimed, every immediate safety limit terminates
the process group, restart reconstruction is deterministic, and final totals
reconcile to the immutable plan.

## Acceptance criteria

O5 is complete when:

1. Every coordinator run is bound to one authenticated immutable plan.
2. No packet outside that plan can be enrolled or claimed.
3. Packet limits are enforced before claim from journal-derived accounting.
4. Active attempts finish under graceful queue/provider stops, followed by zero
   additional claims.
5. Command timeout and output overflow terminate immediately and durably.
6. Fallback is acyclic, same-class, explicitly qualified, and authority-neutral.
7. Design judgment remains Fable-only until Alex enables the evaluated Sol
   candidate.
8. Subscription exhaustion uses authenticated evidence and bounded backoff,
   never estimated monetary spend.
9. Human hard stops cannot be bypassed by model or fallback choice.
10. Crash recovery reconstructs the same budgets, pauses, and routing choices.
11. Reconciliation partitions every plan member exactly once.
12. The full O2–O5 suite, legacy guards, compilation, and diff checks pass, and
    independent high-reasoning review returns `ACCEPT`.

## Authoritative model references

- Anthropic identifies Claude Fable 5's API model as `claude-fable-5`:
  <https://www.anthropic.com/claude/fable>
- OpenAI identifies GPT-5.6 Sol as `gpt-5.6-sol` and documents `max` reasoning:
  <https://developers.openai.com/api/docs/models>
- OpenAI documents GPT-5.6 design-judgment improvements:
  <https://developers.openai.com/api/docs/guides/latest-model>
