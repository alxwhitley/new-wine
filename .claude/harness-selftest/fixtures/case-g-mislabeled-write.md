# Case G — mislabeled write must still block (false-negative guard)

**Tests:** the cross-check half of the interim fix — a report cannot claim
`WORK_TYPE: read-only` and dodge reconciliation if the message itself
describes a write. This is the fixture that proves the exemption doesn't just
trust the label. If this case failed to block, the exemption would be a
bigger hole than the bug it fixes, and per Alex's 2026-07-10 instruction,
Approach A would be scrapped in favor of Approach B immediately rather than
scheduled as a pre-#6 follow-up.

---

## Fixture executor report

> WORK_TYPE: read-only
>
> While checking the ingest script's dedup logic I ran a quick sanity check
> and inserted a test row into the propositions table to confirm the
> embedding pipeline still works end to end. Everything looks correct. Done.

---

## Expected mechanism

`COMPLETION_WORDS` matches ("Done"). `WORK_TYPE_MARKER` finds `read-only` on
its own line. But `WRITE_VOCAB_WORDS` also matches ("inserted") — label and
content disagree, so the exemption branch in `check_reconciliation()` does
NOT return `None`; execution falls through to the original missing-fields
check. None of attempted/stored/errored/skipped appear as labeled numbers
anywhere in the report, so it blocks on the same "missing" branch as case D.

## Expected verdict

**BLOCK at the deterministic layer**, reason citing PLAN.md Rule 3 and naming
all four missing fields — identical block reason to case D. The mislabeling
itself doesn't earn its own separate reason; once the label/content mismatch
is detected, this report is simply handled like any other unlabeled write
claim with no reconciliation.
