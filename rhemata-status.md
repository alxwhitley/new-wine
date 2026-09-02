# New Wine — Live Status

Point-in-time state only. Overwritten each session, never appended to. Durable
truth lives in code, git history, `PLAN.md`, `docs/roadmap.md`,
`docs/plan-archive.md`, and `CLAUDE.md`.

Last verified: 2026-09-02. **PLAN.md has zero active blockers.**

---

## Current state

Production is unchanged. Biblical-depth Phases 0–8 remain merged and deployed
default-off, TIPNR source hidden, `BIBLICAL_CONTEXT_ANSWER_ENABLED` absent on
both Railway services, zero TIPNR propositions, registries empty. **No
production write, embedding purchase, deployment, or feature change happened
this session.** Branch `codex/biblical-ingestion-completion-queue` is pushed
and current at `8c99ea1`; nothing merged to `main`.

**The ingestion queue's central premise was wrong, and that is the session's
main result.** The queue asserted 21 exact-complete TIPNR items with 3,938
remaining. Only 20 are. Phase 6 ingested Aaron (`H0175`) from the reduced
parser fixture, so production holds a 344-character document with **4 of
Aaron's 352 OSIS references** and the artifact's real Aaron projection was
never stored. Alex ruled **"Correct Aaron"**: artifact-Aaron joins the
remaining set and the stale fixture row is retired by demotion. Full landmine
entry in `CLAUDE.md`. Corrected, now-frozen arithmetic:

| | queue asserted | actual |
|---|---|---|
| remaining items | 3,938 | **3,939** |
| batch geometry | 19×200 + 138 | **19×200 + 139** |
| rows | 11,814 | **11,817** |
| after ingest | 3,959 docs/chunks/policies | **3,959 current policies; 3,960 docs/chunks** (1 inert) |

Packets 0–4.1 of `docs/superpowers/plans/2026-09-01-biblical-context-ingestion-completion-queue.md`
are complete, in four build commits:

- `6f64c4a` — full-corpus contract, 20 frozen batches, packet
  `6ec7e6e9dead5ccd2bcc53d5e829a5b2fd4a60dde98a571eb2d24181ea8dc7d6`
- `23bb16a` — zero-effect preview + prefix-resumable read-only preflight
- `ad0ba57` — resolved four Required review findings
- `8c99ea1` — closed review advisories

Independent fresh-context review returned **ACCEPT** after one REVISE round.
Its four Required findings were real and two were serious: the hidden-retrieval
probe had **zero live call sites** while evidence still read `"verified"`, and
global reconciliation was **arithmetically guaranteed to fail** only after the
spend and all 11,817 writes completed. Both fixed and mutation-proven.

Verification at close: 120 checks in the new suite plus all 159 existing
biblical-depth checks green; twelve mutations across both rounds each caught
with files restored byte-identical; preview byte-stable across three runs;
packet and preview hashes unchanged through remediation. Live read-only
preflight: **all_clean at 3,939**, 20 pilot exact-complete, 0 propositions,
source hidden, migration 097 intact, next batch 1.

**One residual, disclosed not hidden:** the `CROSS JOIN LATERAL` retrieval
probe SQL has never executed against a real database. The
`newwine_readonly_analysis` role gets `InsufficientPrivilege` on `app_settings`
inside `match_chunks`/`search_chunks_fts`, and the retrieval path needs the
service credential, which was not authorized pre-gate. Both LATERAL shapes and
both RPC signatures were verified read-only; the authorized rollback probe is
its first real execution.

Evidence (ignored, mode 0600) in `local/2026-09/`: `pkt0_census.json`,
`pkt0_finding_h0175.json`, three inventory rebuilds, `pkt2_preflight.json`,
`pkt4_gate_preflight.json`.

Also pushed this session: Alex's parallel frontend work (`cc6ba97`, `73fa130`,
`acdd971`, `04c178d`, `5de5ef7`) — heading hierarchy, responsive WebKit matrix,
tablet navigation, mobile-keyboard composer. A physical-iPad composer check
with the software keyboard open remains that track's open verification.

---

## Session outcome and measures

- Original outcome: **stopped at the queue's own attended gate, as designed** —
  every repository-only, local, and read-only step is complete and reviewed.
- Acceptance: **passed** — 120 + 159 checks, twelve mutation proofs, reviewer
  verdict ACCEPT, live preflight all_clean.
- Unplanned investigations started: **0**.
- Findings promoted to Blocker: **0** (the H0175 defect blocks the A4 queue,
  not beta; feature is off and the source is hidden, so there is no exposure).
- Active critical-path item at close: **1** — ATTENDED GATE TIPNR, awaiting
  Alex.
- Scope changes approved by Alex: the "Correct Aaron" ruling, and the push +
  session close.

---

## Next single item

**Answer the TIPNR approval gate.** Five operations were presented as one
consolidated request at commit `8c99ea1`; none is authorized yet:

1. Rollback-only probe of batch 1 — 600 staged rows, always rolled back, zero
   model calls.
2. Paid embeddings — ≤ 3,939 requests, ≤ **$0.02441808** (est. $0.0086),
   `text-embedding-3-small`, 1536 dimensions.
3. Twenty batch transactions — 3,939 items, 11,817 rows.
4. **Irreversible** one-row demotion of the stale Aaron policy, chunk
   `77f1581b-3225-5110-887b-9b651ebf9adf` (migration 097 permits only
   `true→false`; recovery needs a new policy row, not a reversal).
5. Final fresh read-only reconciliation.

Excluded from that request and still requiring separate approval: feature
enablement, visibility change, protected/plural registry or doctrinal
assignment, live paid answers, OpenBible or any other source, and
merge/deploy. A staged "probe only" answer is available and runs operation 1
alone.
