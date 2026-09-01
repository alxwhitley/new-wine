# New Wine — Live Status

Point-in-time state only. Overwritten each session, never appended to. Durable
truth lives in code, git history, `PLAN.md`, `docs/roadmap.md`,
`docs/plan-archive.md`, and `CLAUDE.md`.

Last verified: 2026-09-01. **PLAN.md has zero active blockers.** Remote `main`
remains at `12cb253`. Biblical-depth Phases 0–4 are on
`codex/biblical-depth-phases-0-3` in PR #3 and are not merged.

---

## Current state

**Biblical-depth Phases 0–4 are complete in repository scope.** The Phase work
in PR #3 spans 18 commits (`c5ee5e0` through `a599812`) covering the approved
rights and provenance manifests, source-use policy, hidden zero-write
TIPNR/OpenBible preview tooling, deterministic passage classification,
migration 097, and the default-off routing/retrieval contract. The branch is
pushed; `main` remains at
`12cb253` and the PR is not merged.

The governing boundary remains unchanged:

- protected Spirit-filled/charismatic topics use only Alex-approved house
  material;
- general biblical/history context may use narrowly approved structured
  fields;
- other orthodox disputes require registered plural presentation rather than
  corpus-majority inference;
- model passage classification is refused in V1;
- mixed, uncertain, absent, prohibited, and unknown passage classifications
  fail closed.

**Phase 4 is implemented but inactive.** `BIBLICAL_CONTEXT_ANSWER_ENABLED`
defaults to false, so the live behavior remains the existing blanket
commentary exclusion and does not query migration 097. If separately enabled
later, the route contract fails closed: protected routes accept no general
commentary/reference material and require exact topic-approved source IDs;
general reference passages require current eligible policy; registered plural
issues require two distinct registered slots and source IDs or return fixed
corpus-gap wording before generation. Cache identities include the effective
flag state, every neighbor is independently rechecked, and a house paper can
never be the sole answer substrate.

**Migration 097 is committed but unapplied.** It creates the internal
`source_passage_policy_versions` table with closed-set and metadata-coupling
constraints, one current row per chunk, append-only history, RLS, and no
`anon`/`authenticated` access. The service role is limited to
SELECT/INSERT/UPDATE and cannot DELETE or TRUNCATE policy history. Applying the
migration remains a separate attended production-write approval, followed by
fresh verification through `newwine_readonly_analysis`.

**Phase 4 verification passed locally without database, network, or model
calls:** 21/21 routing tests, 16/16 source-use policy tests, 7/7 passage-policy
tests, Python compilation, quote-selection and quote-rail regressions,
commentary exclusion, answer-latency contract tests, the async-serving gate,
and the no-cost position-paper Tier A checks. An independent answer-integrity
review returned `ACCEPT` after five fail-closed corrections were added.

**No source registration, ingestion, visibility change, classification batch,
migration application, feature enablement, live answer, production database
write, or manual deployment occurred.** The protected-source and plural-
viewpoint registries remain deliberately empty pending Alex's separate
doctrinal/source decisions.

User-owned modified and untracked files already present in the shared worktree
were left untouched and remain outside PR #3.

---

## Session outcome and measures

- Original outcome: **completed** — approved Phase 4 design, governing-text
  replacements, and default-off routing/retrieval implementation.
- Acceptance: **passed** — all Phase 4 criteria and the independent review's
  five corrections have local mocked proof; the final review returned
  `ACCEPT`.
- Unplanned investigations started: **0**.
- Findings promoted to Blocker: **0**.
- Active critical-path item at close: **0**.
- Scope changes approved by Alex: the Phase 4 design and exact CLAUDE.md /
  ARCHITECTURE.md governing replacements. No production authority was added.

---

## Next single item

**Phase 5 — prompt and generation contract, later.** Begin a future session
with one bounded design and read-only diagnostics. Phase 5 must preserve the
Phase 4 pre-writer routing boundary and independently specify how labeled
general-reference and plural-viewpoint context may influence generation and
verification. No Phase 5 code, registry assignment, migration application,
feature enablement, live answer, deployment, or production write is currently
authorized.
