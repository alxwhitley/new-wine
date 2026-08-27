# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-27. **PLAN.md has zero active blockers.** This session
shipped one UI fix and closed out the B6 general-latency track end to end
(measured, reviewed, decided, deployed) — see PLAN.md/docs/roadmap.md for the
pointer, full trail in `docs/audits/2026-08/b6_answer_latency_session_2026-08-25.md`.

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**Sources disclosure toggle — DONE, live (commit `3f75d2b`).** The citation
fallback list (shown when an answer's citations aren't referenced inline as
`[N]`) rendered fully open by default. Now a closed `Sources (N)` button with
a chevron; the list only mounts on click. Verified via a dev-only preview
page (blocked in prod) since the fallback path doesn't fire on most answers.
Deployed to Vercel, confirmed 200 on `rhemata.app`.

**B6 general answer-latency — DONE, live (commits `07f6922`, `98748ed` →
`f00b303`).** Every real answer now generates with Anthropic's
`output_config.effort="medium"` instead of the implicit `high` default —
hardcoded, not flag-gated (Alex's explicit call: this affects every answer,
not a narrow edge case, so the flag machinery wasn't judged worth it).
Measured **25.46% faster median producer time** (49.41s → 36.83s), 11/12
cases faster, no p90 regression, on the fixed 12-case paired benchmark (48
paid generations, ~$2.67 total). A targeted 6-pair blind human quality
review across the doctrinally sensitive categories (healing, prophetic
accountability, apostolic authority, eschatology, baptism, tongues) found
**zero hard failures** on either variant — the one flagged minor concern
turned out, after unblinding, to belong to the old baseline, not the
candidate. Both Railway services (`rhemata`, `answer-worker`) confirmed
redeployed and healthy; `answer-worker` logs show `fake=False` (the real
`produce()` path). Full trail, including the rejected `teacher_specific_v1`
candidate this superseded (kept as B6-F1, a separate named-teacher integrity
fix, unaffected by this): `docs/audits/2026-08/b6_answer_latency_session_2026-08-25.md`.

**Worth watching, not a known problem:** the blind review was 6 pairs, not
24 — a real but small sample. If a real answer reads unusually thin or
hedge-y going forward, this is the first place to look; reverting is a
one-line code change (`GENERATION_EFFORT` in `producer.py`).

**Quote rail:** still off (`QUOTE_SELECTION_ENABLED=false`), unchanged.

---

## Findings surfaced, not yet acted on

- **Scheduled**: quote accuracy/relevance repair before any attended
  re-enable.
- **Scheduled A2:** correct the omitted New Wine article + two
  continuations, rerun local no-write gates.
- **Triggered**: JWKS unknown-`kid` rate limit — residual belongs at the
  edge.
- **Repo hygiene, unresolved across multiple sessions now:** two loose ends
  sitting in the working tree, neither touched this session because their
  origin/intent is unclear —
  `frontend/components/rhemata/chat-input.tsx` has an uncommitted one-line
  CSS change (drops the focus ring on the prompt cluster), and migration 091
  plus its three scripts (`apply_migration_091.py`,
  `flip_teacher_specific_routing_flag.py`, `test_teacher_specific_routing_flag.py`)
  were applied live for B6-F1 but never `git add`ed. Both are low-risk to sit
  as-is; worth a deliberate decision (commit or discard) next time someone's
  in this area.
- Carried, not re-checked this session: `scripts/test_metering.py` writes
  live to production despite the `test_*.py` naming (self-cleans, verified
  zero residual, but read any `scripts/test_*.py` before batch-running it);
  dependency/hardening follow-up (starlette+fastapi, pdfplumber+pdfminer,
  CSP, deferred Next.js major bump); staging source name still reads
  `"Vlad Savchuk (web staging)"`; Bonnke URL suspect; no retention/TTL logic
  for user data; `rhemata_readonly_analysis` has no grant on PII/user
  tables; full cascading account deletion still unbuilt.

---

## Next single item

**No active blocker.** Both items this session shipped are fully closed and
live. Next work is whatever Alex prioritizes from `docs/roadmap.md`'s
Scheduled list (quote accuracy/relevance repair, New Wine A2 correction, the
B1–B7 product track) — none is currently authorized as a Blocker. Active
blocker count **0**.
