# Long-Conversation Handoff

**Date:** 2026-08-26

**Status:** Phases A-D implemented 2026-08-26 (unit + threshold confirmed by
Alex; code written, type-checked, linted, unit-tested). Migration 092 is
written and dry-run verified but **not applied** — that's a separate
attended DB-write step. Copy is draft-only, not yet reviewed. Live/E2E
verification not done — see Phase F. Answers `docs/roadmap.md` Horizon item
6: "Long-conversation handoff with a token trigger, provenance, privacy, and
user control." This spec is that item's required "fresh specification"
gate; landing this document (and the code above) does not itself promote
the item to Scheduled in the roadmap file — that's still Alex's call, and
chat doesn't edit `docs/roadmap.md` directly per the Project Knowledge Read
Contract.

**Scope:** A UX nudge in Rhemata's own end-user chat (not this coding-agent
session, and not this repo's Claude Code usage). Trigger threshold decided
by Alex before build; touches frontend + a schema addition + backend
plumbing; no LLM calls, no corpus, no theological content.

## Objective

Rhemata conversations have no signal today that they've gotten long, and no
nudge to start fresh. Two things worth fixing:

1. **Beta spend control (co-primary — Alex is personally paying every
   beta user's API cost, confirmed 2026-08-26).** Every turn is a real
   paid generation (median $0.039/answer, CLAUDE.md Settled #14) with no
   per-conversation ceiling or visibility today, and during private beta
   that spend lands on Alex directly, multiplied across however many
   invited beta users are active — this is live financial exposure, not
   a hypothetical. **Important correction to keep the copy honest:**
   `_build_history()` (`backend/app/services/async_answers/producer.py:510`)
   already caps the history sent to the model at the last 6 messages, so
   per-turn cost does **not** compound as a conversation grows — it stays
   roughly flat. The real spend growth is purely additive (more turns ×
   flat per-turn cost, per conversation, per user), not accelerating.
   Nudge copy must not claim the conversation is "getting expensive to
   continue" — that's not true and a technical user could notice. But
   "additive, unbounded, multiplied across every beta user, and paid by
   Alex" is a real reason to want a lever now, during beta specifically —
   this is the near-term driver for prioritizing the feature at all, even
   though the mechanism is milder than "each message costs more."
2. **Product fit (the reason to keep this as a soft nudge rather than a
   hard cap).** CLAUDE.md's own design filter: "Time-in-app is not a
   success metric — the goal is sending users back to real teachers and
   real churches... A feature that makes a user say 'I don't need my
   pastor, I have Rhemata' gets killed." An unboundedly long single
   back-and-forth is the shape this line warns against. This is why the
   fix is a dismissible "consider starting fresh" nudge and not, say, a
   hard per-conversation cap that would read as the product rationing
   itself — the philosophy constrains the *shape* of the fix; the beta
   budget is why it's worth building now.

Feature: once a conversation crosses a threshold, show a dismissible card
— modeled directly on the existing `WeeklyLimitCard`
(`frontend/components/rhemata/weekly-limit-card.tsx`) — suggesting the user
start a new conversation, with a "Start a new conversation →" action wired
to the existing `clearMessages()` (`frontend/hooks/useChat.ts:302`).
Nothing about retrieval, generation, or the answer path changes.

## Goals (user)

- A user in a long-running conversation gets an early, low-friction,
  truthful signal that starting fresh is worth considering.
- Alex gets visibility into accumulated per-conversation spend without a
  hard block.
- The nudge never invents urgency that isn't real.

## Non-goals (this design)

- Auto-summarizing or carrying prior conversation content into the new
  conversation. A generated summary of already-cited answers, reused as
  context in a new conversation, is itself an ungrounded claim about what
  was previously said — exactly the kind of thing this product's citation
  discipline exists to prevent. **This is the actual answer to the
  "provenance" question in the Horizon item title: v1 has no provenance
  design to make, because nothing propagates.**
- Hard-blocking further messages at the threshold. The existing weekly/
  guest query limits already hard-block; this is a softer, earlier signal
  layered on top, not a replacement.
- Any change to `_build_history`'s 6-message cap or to per-turn generation
  behavior.
- Deleting, archiving, or hiding the old conversation. It stays exactly as
  it is; the user opens a new one alongside it.
- A guest (session-storage-only) trigger in v1 — see Scope below.

## Open questions for Alex (blocking a build go-ahead)

1. **Unit.** The roadmap item says "token trigger" literally. I'd recommend
   showing a **dollar estimate** instead (derived from the same tokens,
   using `config.py`'s existing `estimate_cost_usd`-shaped function) —
   raw token counts mean nothing to a non-technical user, and "you've spent
   about $0.60 in this conversation" is the honest version of what you
   asked for ("save on money"). Confirm which unit you actually want
   surfaced, if any — a pure **turn-count** trigger is also on the table
   and needs zero new schema (see Phase A below).
2. **Threshold value.** No number yet. Rough anchor for discussion: at the
   $0.039 median/turn, ~$0.50 cumulative ≈ 12-13 turns — not a
   recommendation, just a starting point to react to. Given you're
   personally covering beta spend, you may want this tighter than a
   mature-product default would be — your call, not an engineering one.
3. **Guest scope.** Build a client-only turn-count estimate for guests now,
   or skip guests in v1 since they already hit the existing weekly-limit
   gate? I'd default to skip-for-v1 — your invited, authenticated beta
   users are the population this feature actually needs to reach for the
   beta-spend reason above, not anonymous guests.
4. **Schema shape.** Per-message `input_tokens`/`output_tokens` columns on
   `messages` (auditable, recomputable) vs. one running
   `conversations.cumulative_cost_usd` counter (cheaper to read, matches
   the existing `provider_rate_usage` running-counter pattern from
   migration 078)? I'd default to the running counter unless you want
   per-message audit granularity.
5. **Copy.** Who writes the actual nudge text — you, or should I draft
   candidate copy against PRODUCT.md's brand register for your review?
6. **Hard cap later?** v1 has none by design (Non-goals). Worth recording
   now whether a v2 hard cap is ever wanted, or explicitly never.

## Trigger design (proposed, pending answers above)

- Primary signal (recommended): cumulative estimated cost across every
  generation in this conversation, computed from summed
  `input_tokens`/`output_tokens` across the conversation's `answer_jobs`
  rows, run through `config.py`'s existing cost-per-token constants.
- Fallback / v0 signal: raw turn count (`messages.length`) — already
  available client-side today with zero new plumbing, usable as a
  placeholder while the token-plumbing schema work (Phase B) lands.
- Whichever signal ships, the number is computed server-side (or from data
  the server already returns) and never requires reading conversation
  *content* to decide whether to show the nudge — see Privacy below.

## Data / schema needed

Confirmed by reading the current code — this is real, not assumed:

- `answer_jobs` already carries `input_tokens`/`output_tokens` per
  generation (`migrations/078_async_answer_path.sql`,
  `backend/app/services/async_answers/jobs.py:262-289`).
- Nothing currently rolls that up per-conversation. `save_exchange()`
  (`backend/app/services/async_answers/conversation_store.py:73`) takes
  `job_id` but does not receive or persist token counts, and the
  `messages`/`conversations` tables have no cost/token columns today.
- Needed: thread the job's `input_tokens`/`output_tokens` (already read by
  `async_chat.py`'s result handler, which calls `save_exchange` at
  `backend/app/routers/async_chat.py:228`) into `save_exchange()`, and
  either write them onto the assistant message row or increment a running
  counter on `conversations` — see Open question 4.
- Guest conversations live only in `sessionStorage`
  (`frontend/hooks/useChat.ts`, `lib/guest-chat-session`) — no server row
  exists to hang a cumulative counter on. This is why guest scope is an
  open question, not an oversight.

## Provenance & privacy (the two words named in the Horizon item)

- **Provenance:** nothing from the old conversation is carried into the
  new one — no summary, no citation reuse, no evidence reuse. A fresh
  conversation starts exactly as empty as clicking "New chat" does today.
  There is no propagation to design a provenance story for.
- **Privacy:** the trigger reads only aggregate cost/turn numbers already
  computed for metering elsewhere in the codebase (`config.py`'s cost
  estimator, the `provider_rate_usage` pattern) — showing the nudge
  requires no new reading of conversation *text*. The number is either
  already client-known (turn count) or returned as a single aggregate
  alongside the existing chat response payload, not fetched from a new
  endpoint that reads full conversation content.

## User control

- Dismissible per-conversation, matching `WeeklyLimitCard`'s existing
  pattern of never blocking the primary action (send message).
- No hard cap in v1 (Non-goals). Sending more messages after the nudge
  remains fully possible.
- Dismissal should not reappear immediately on the very next turn — needs
  a minimum re-nag interval (e.g., N more turns/dollars) so it isn't
  naggy; exact value TBD alongside the threshold (Open question 2).

## Architecture

```text
Turn N completes
        │
        ▼
async_chat.py result handler
  (already reads the job's input/output tokens)
        │
        ▼
save_exchange()  [extended]
  writes/increments conversation-level cumulative signal
        │
        ▼
result payload includes running cost estimate / turn count
        │
        ▼
useChat.ts surfaces it in hook state
        │
        ▼
page.tsx renders <ConversationLengthNudge>
  (sibling of WeeklyLimitCard) once threshold crossed
        │
        ▼
"Start a new conversation →" → existing clearMessages()
```

## Cost

N/A — no LLM calls in this feature; it's UI + plumbing over data the
answer path already produces. The $50 corpus-run ceiling and named-estimate
rule don't apply here; noted explicitly so it isn't mistaken for a skipped
step.

## Phased delivery

| Phase | Work | Status |
|---|---|---|
| **A** | Alex answers the open questions | **DONE 2026-08-26** — unit: estimated dollars. Threshold: $0.50 (~13 turns). Defaults accepted for the rest (running-counter schema, skip guests in v1, no hard cap, draft copy for review). |
| **B** | Schema: `migrations/092_conversation_length_signal.sql` (`conversations.cumulative_input_tokens` / `cumulative_output_tokens` / `turn_count`, all `NOT NULL DEFAULT 0`); `save_exchange()` threads token usage through with a reconnect-safe idempotent increment (gated on `cur.rowcount == 1` on the assistant-message insert, not assumed) | **DONE — applied to production 2026-08-26** (attended, Alex-approved). `scripts/apply_migration_092.py --apply` ran live; its own 10-check verify pass confirmed all three columns exist, `NOT NULL`, default `0`, and zero existing rows backfilled to NULL. `scripts/test_conversation_length_signal.py` proves the idempotency gate against a fake cursor, including a sensitivity check that a broken gate would double-count (12/12 passing). |
| **C** | API: `async_chat.py`'s `/result` endpoint computes `conversation_cost_usd` (via `config.estimate_cost_usd`) and `conversation_turn_count` from the returned totals, includes both in the SSE payload; `null` for guests (no server-side conversation row, matching v1 scope) | **DONE.** Compiles clean (`py_compile`). |
| **D** | Frontend: `ConversationLengthNudge` (`frontend/components/rhemata/conversation-length-nudge.tsx`, `WeeklyLimitCard` pattern); `StreamMeta`/`useChat.ts` plumbing; wired into `page.tsx` (suppressed under the hard weekly-limit stop and while a turn is streaming; dismiss resets on new/switched conversation) | **DONE.** `tsc --noEmit` clean; `npm run lint` introduces zero new errors/warnings (verified by diffing lint output against the unchanged line ranges). |
| **E** | Copy: nudge text reviewed against PRODUCT.md brand register; must not claim "getting expensive" | **Draft only, not reviewed.** Current copy deliberately says nothing about cost/tokens — see the component file's own comment. Needs Alex sign-off. |
| **F** | Regression test + manual verification in a real conversation | Backend logic test done (12/12). **Live browser/E2E verification NOT done** — blocked on Phase B's migration actually being applied (the `conversations` table doesn't have the new columns in production yet), and a real run costs real generations. Needs Alex's call on when/how to do this. |

## Risks and constraints

- **A dismissible nudge is a soft lever, not a spend cap.** If a user
  ignores it, total spend on that conversation keeps growing exactly as it
  would today — this feature reduces expected spend at the margin (some
  users will take the hint), it does not bound it. If the real goal is a
  guaranteed ceiling on beta spend, that needs a hard cap or a lower
  existing query-limit number, a different (and non-goal-excluded)
  mechanism from this spec. Confirm the nudge is meant as a behavioral
  complement, not the actual cost-control backstop, before treating this
  spec as "the beta-cost fix."
- **Possible overlap with the existing weekly query-limit system**
  (`enforce_query_limit`, `WeeklyLimitCard`, `weeklyUsage` state in
  `page.tsx`) — that mechanism may already be the primary spend backstop
  for authenticated users. Worth checking whether it already caps
  per-user beta cost adequately before investing in a second, conversation-
  scoped mechanism; if so, this feature's job narrows to the product-fit
  goal (Objective #2) and its cost-control value is smaller than it first
  looks.
- Nudge copy must not misstate the actual cost mechanism (no per-turn
  compounding, confirmed above) — a technically-aware user noticing the
  claim is false costs trust.
- Guest scope gap (no server-side conversation row) may leave guests
  unserved in v1 — acceptable, since guests already hit the existing
  weekly-limit gate; needs Alex's explicit sign-off, not a silent gap.
- Threshold must not be so low it interrupts a genuine single Bible-study
  line of questioning — the product's actual desired use case is a
  focused multi-turn conversation, not a one-shot query. This needs Alex's
  number, not an engineering guess.
- This is a **Repo-only multi-step build** per the Session Routing table
  (CLAUDE.md) for Phases C-F; Phase B's migration apply is a separate,
  attended **Database-write** session under the repo's hard rule — never
  delegated to a subagent.

## Files likely touched (planning hint)

- New migration: token/cost columns on `messages` or `conversations`
  (attended apply)
- `backend/app/services/async_answers/conversation_store.py::save_exchange`
  — thread token usage through
- `backend/app/routers/async_chat.py` — pass the job's token usage into
  `save_exchange`; include the running total in the result payload
- `frontend/hooks/useChat.ts` — surface running cost/turn count in hook
  state
- New `frontend/components/rhemata/conversation-length-nudge.tsx`
  (sibling of `weekly-limit-card.tsx`)
- `frontend/app/page.tsx` — render the nudge; wire to existing
  `clearMessages()`
- Tests: token-plumbing regression, threshold-crossing unit test
- `docs/roadmap.md` — once Alex reviews this spec, record the promotion
  decision (Scheduled vs. still Horizon) there; chat does not self-promote

## Approval trail

**2026-08-26:** Alex confirmed unit (estimated dollars) and threshold
(~$0.50 / ~13 turns) after real-usage context (only 2 users had ever
queried, near-zero real spend to date — this feature is "ready before it's
needed," not an urgent fix). Alex directed implementation ("no lets
implement"); remaining open questions (guest scope, schema shape, hard cap,
copy ownership) were defaulted per this spec's own recommendations rather
than asked individually, given the fast pace of the session — flagged here
for Alex to override anything he'd have answered differently.

**Still pending Alex:** migration 092 apply (attended DB write); copy
review (Phase E); live/E2E verification approach (Phase F).
