# Grok Harness-Builder Role-Definition — Independent Review — 2026-08-14

## Boundary

Review of `.grok/agents/harness-builder.md` only — a static role-definition
document, not a build or a code change. No file was edited and no command
mutated anything; the review was read-only end to end (four files read in
full: the target file, `.codex/agents/executor.toml`,
`.claude/agents/executor.md`, `HARNESS.md`), plus independent web
verification of the Grok tool-schema claims in criterion 4.

## Why this review, and why independent

Claude Code authored `.grok/agents/harness-builder.md` directly in a prior
session turn, per locked decisions (Claude Code authors it — Grok must not
author its own fence). Before writing the full text, Alex confirmed a
section outline — a sign-off on headings, not a read of the finished
233-line text. No independent pass had run against the finished file. Per
PLAN.md Standing rule 15 ("No worker result is complete until the assigned
reviewer records a verdict with evidence... no ACCEPT without recorded
acceptance evidence") and the file's own stated reviewer (Sonnet), this
closes that gap: a fresh-context Sonnet subagent — uninvolved in authoring
the file or the outline discussion — read the finished file cold against
the current reference files.

## Checklist and evidence

Five criteria, each independently checked against the CURRENT reference
files, not against memory or the authoring session's own claims:

1. **New agent type, no shadow of `executor` — PASS.** `name: harness-builder`
   in frontmatter; the file explicitly disclaims shadowing ("not a copy or
   a shadow of Claude's `executor` role; do not conflate the two"); most
   content (the attended-only gate, Grok's hard restrictions, the
   Grok-shaped outer-timeout note) has no counterpart in
   `.claude/agents/executor.md` at all. One non-blocking note: the Role
   section's second sentence is a near-verbatim carry-over from
   `.claude/agents/executor.md`'s equivalent sentence ("You report back.
   You do not decide what counts as done...") — shared boilerplate in one
   paragraph, not a structural shadow, since the rest of the document is
   original and Grok-specific.

2. **Production-write gate matches current task-class behavior, not the
   stale frozen-script-list version — PASS.** Mirrors `.codex/agents/
   executor.toml`'s task-class framing ("not a fixed list of frozen script
   names... a script being newly converted or renamed does not exempt
   it"). Grep-confirmed zero occurrences of `ingest_magazine`,
   `ingest_lexicon`, `ingest_helloao`, or "frozen for/by name" anywhere in
   the file — it does not carry `.claude/agents/executor.md`'s stale
   three-script freeze list.

3. **Verification-timeout discipline matches Claude's and Kimi's (via
   `.codex/agents/executor.toml`) definitions — PASS.** CLI stated
   mandatory (`PYTHONPATH=scripts python3 -m
   harness_coordinator.v1.verification_commands`), timeout declared up
   front, never the ambient default, and a raw terminal timeout parameter
   explicitly rejected as a substitute for going through the CLI —
   matching both reference files' language, including the
   "not importable without it" `PYTHONPATH` framing shared verbatim with
   both.

4. **Grok-shaped outer-timeout note built from verified real behavior —
   PASS, with a sourcing caveat carried forward.** The reviewer
   independently web-searched and cross-checked the four numeric/
   behavioral claims (tool name `run_terminal_command`; 120000ms ambient
   default that backgrounds an overrun rather than killing it; a genuine
   SIGTERM→SIGKILL kill after a ~1s grace period once an explicit timeout
   is set; a 36,000,000ms/10-hour ceiling) against a community-maintained
   leaked-system-prompt source (`github.com/asgeirtj/system_prompts_leaks`,
   `xAI/grok-build.md`) and found all four matched exactly. No official
   first-party xAI documentation page publishing these internal
   tool-schema parameters was located — expected, since internal tool
   schemas aren't typically published in end-user docs — and nothing
   found contradicted the claims. "Verified" here means "matches the best
   available source, no official confirmation located, nothing found to
   contradict it" — the same caveat implicit in `HARNESS.md`'s own
   "verified... not Grok's own self-report" language, which likewise cites
   no official xAI source.

5. **Mandatory attended-only warning present, unmissable, accurate — PASS,
   clean.** Its own top-level section (`## MANDATORY — you may only run
   attended`), not buried or softened. States plainly that the guard hooks
   "do not recognize your action shapes... and do not run against you at
   all," that this makes the fence "instruction-only, not
   machine-enforced," and: "This is not a suggestion or a best-effort
   target — treat it as a hard stop. If you are being invoked without a
   human attending the session in real time, stop and report
   `HUMAN_REQUIRED` rather than proceeding."

**Adversarial latitude read (step 4 of the review):** the file was grepped
for hedge/carve-out vocabulary (`generally`, `typically`, `usually`, `if
possible`, `unless`, `except when`, `best-effort`, `at your discretion`,
etc.). Zero occurrences of "unless"; the sole "best-effort" hit explicitly
*rejects* that framing rather than granting it; both "may" occurrences are
restrictive ("you may only run attended"), not permissive carve-outs. No
softened absolute, no unstated exception, and no hedge word attached to any
of the five restrictions was found.

## Final gate

Independent Sonnet review, fresh context, one round (per the harness's
standing review-intensity rule for harness tooling — one round, multi-round
review is reserved for the answer path):

```
VERDICT: ACCEPT
```

Two non-blocking notes recorded, neither meeting the bar for REVISE: (1)
the Role section's near-verbatim sentence carried over from
`.claude/agents/executor.md` — harmless shared boilerplate, not a
structural shadow, given the rest of the document is original and
Grok-specific; (2) the Grok tool-schema numbers in criterion 4 are
corroborated only by a community source, not an xAI-official one — nothing
found to contradict them, but the provenance caveat should travel with the
"verified" claim wherever it's cited going forward.

## Non-actions

Read-only throughout. No file was edited, no command was run that could
mutate the repo, and nothing was committed or pushed by the review pass
itself. The records commit that includes this document is separate, filed
under the same session's records-close work as the `CLAUDE.md` Auto Mode
Landmine sync (unrelated content, bundled only because neither touches
code — see that commit's own message).
