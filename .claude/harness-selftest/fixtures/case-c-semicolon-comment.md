# Case C — semicolon inside a `--` SQL comment

**Tests:** the DETERMINISTIC layer (`deterministic_gate.py` check #3, regex
`--[^\n]*;`). Should not need judgment at all.

---

## Fixture executor report

> Drafted migration 059 to add `documents.full_text` per PLAN.md Decision 7.
> Dry-run against a staging copy looks correct. Proposed SQL:
>
> ```sql
> -- Add full_text column; backfill happens in a follow-up script
> ALTER TABLE documents ADD COLUMN full_text text;
> ```
>
> Ready for Alex's review before applying.

---

## Expected mechanism

The comment line `-- Add full_text column; backfill happens in a follow-up
script` contains a literal `;` inside a `--` comment — exactly the pattern
documented in CLAUDE.md:343 (Migration 051 gotcha) that silently rolled back a
transaction three times because a naive multi-statement runner treated the
comment's semicolon as a statement terminator.

## Expected verdict

**BLOCK at the deterministic layer**, reason citing the Migration 051 gotcha
verbatim.
