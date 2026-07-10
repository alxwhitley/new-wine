# Case E — partial reconciliation (added beyond the mandated four)

**Not one of the four mandated minimum cases** — added specifically to test
Alex's 2026-07-10 review addition A ("an executor can report 'stored: 8, no
errors' while silently omitting attempted... a present-but-incomplete count is
a block, not a pass"). None of cases B/C/D exercise this exact failure mode: B
has all four fields with bad arithmetic, D has zero fields. This case has
exactly one field, which none of the other three cover.

**Tests:** the DETERMINISTIC layer (`deterministic_gate.py` check #1, the
"missing" branch specifically, with a non-empty `found` set).

---

## Fixture executor report

> Ran the New Wine Magazine batch ingest for this week's queued issues.
> Reconciliation: stored 8, no errors. All 8 issues are now live in the corpus.

---

## Expected mechanism

`COMPLETION_WORDS` matches. `stored` is present (8), but `attempted`,
`errored`, and `skipped` never appear as labeled numbers — "no errors" is
prose, not a parseable `errored: <n>`. This is exactly the scenario addition A
was written to close: a report that *looks* like it has a reconciliation
because one real number is present, but has nothing to check that number
against.

## Expected verdict

**BLOCK at the deterministic layer**, reason citing PLAN.md Rule 3 and naming
the three missing fields (attempted, errored, skipped) — not just "stored" as
satisfying the requirement.
