# Case H — no WORK_TYPE marker at all, fail-closed (unchanged behavior)

**Tests:** that the interim fix's default is genuinely fail-closed — a report
that reads exactly like the #4 false positive (ordinary completion language
describing what sounds like read-only work) but never declares a `WORK_TYPE`
marker at all gets no benefit of the doubt. The exemption requires an
explicit, correctly-labeled, content-consistent declaration; silence does not
imply read-only.

---

## Fixture executor report

> Reviewed the auth flow end to end and checked every call site for stale
> config. Everything checks out cleanly. Done.

---

## Expected mechanism

`COMPLETION_WORDS` matches ("Done"). `WORK_TYPE_MARKER` finds nothing — there
is no `WORK_TYPE:` line anywhere in the report. The exemption branch in
`check_reconciliation()` requires a marker to even evaluate the read-only
path; with `marker` being `None`, that branch is skipped entirely and
execution falls straight through to the original missing-fields check,
unchanged from before the fix.

## Expected verdict

**BLOCK at the deterministic layer**, reason citing PLAN.md Rule 3 and naming
all four missing fields — identical in mechanism and reason to case D. This
fixture is deliberately the same shape as the real #4 incident's report
style, to prove the fix doesn't become lenient on read-only-*sounding* prose
in general — only on prose that explicitly, correctly, and consistently
declares itself.
