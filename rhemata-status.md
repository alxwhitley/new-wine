# New Wine — Live Status

Point-in-time state only. Overwritten each session, never appended to. Durable
truth lives in code, git history, `PLAN.md`, `docs/roadmap.md`,
`docs/plan-archive.md`, and `CLAUDE.md`.

Last verified: 2026-09-04. **PLAN.md has no active blockers.**

---

## Current state

**B8 is DONE and live.** Repository commit `d1ac57a` enforces Settled #17 by
rejecting attributed prose quotations of five or more words while preserving
the existing Scripture, hypothetical, short-term/scare-quote, and unattributed-
prose exclusions. The existing regenerate-once-then-refuse behavior remains.

Alex approved an attended, isolated backend-only Railway release because local
`main` was 35 commits ahead of `origin/main` with unrelated unpublished work.
The API deployment `8d2a8c4e-961a-4c1a-872c-68164f75b133` and answer-worker
deployment `dc2d70d1-d1b5-4d4e-b3c0-247f935f728e` both reached `SUCCESS`.
The public API health check passed. No Git push, Vercel deployment, migration,
or corpus write occurred.

The attended guest smoke job `e8d29d61-ec7d-4b28-a2e9-ab2513749579`
completed `outcome=answered` with 3,326 characters and seven citations. An
independent refetch ran the served answer through the repository guard and
found zero prohibited quotations. The first generation conformed, so the live
retry branch did not activate; deterministic retry/refusal behavior remains
covered by the 17 generation-contract tests.

Two `search_chunks_fts` calls logged HTTP 500 during retrieval, but the path
failed soft and completed normally. With no demonstrated user-visible failure
or B8 causal link, this is Parked in `docs/roadmap.md` rather than promoted.

---

## Session outcome and measures

- Original outcome completed: **yes** — B8 was deployed and verified live.
- Unplanned investigations started: **0**.
- Findings promoted to Blocker: **0**; one adjacent observation classified
  Parked.
- Scope changes approved by Alex: isolated backend-only Railway deployment in
  place of publishing the unrelated Git/Vercel backlog.
- Active critical-path item count: **0**.

---

## Next single item

No active Blocker. The next authorized Scheduled item is the representative
Ravenhill source-quality comparison in `docs/roadmap.md`; any production corpus
action remains an attended gate.
