# Corrections to standing findings — 2026-08-24

Four items carried in `rhemata-status.md` as open findings were investigated
before being acted on. Three turned out not to need work, and one widely
repeated claim about a governing document turned out to be **wrong in the
direction of weakening a real caveat** — recorded here so the caveat is not
weakened by a future session reading the same superficial evidence.

All checks below are read-only: live SELECTs via the
`rhemata_readonly_analysis` role, plus code reads. No database write, no
spreadsheet write.

## 1. CLAUDE.md's "2,409 legacy propositions have NULL provenance
permanently" is CORRECT — do not "fix" it

**A subagent research pass this session claimed the opposite** — that a live
query showed "zero rows with missing provenance out of 11,175," that the
2,409 now carry `legacy_unknown`, and that the CLAUDE.md entry should
therefore be corrected because "something backfilled them." That claim was
checked directly against the live database and **does not hold**:

```
propositions total: 11175
  NULL prompt_version:     0
  NULL prompt_fingerprint: 2409
  NULL model:              2409

by prompt_version:
  v3.1              8544
  legacy_unknown    2409
  v3                 222
```

Only `prompt_version` was ever backfilled, and it was backfilled to the
literal sentinel string `legacy_unknown` — a label whose meaning *is*
"unknown." The two columns that carry actual provenance,
`prompt_fingerprint` and `model`, are **still NULL on exactly those same
2,409 rows**. Nothing was recovered. The substantive fact CLAUDE.md records —
that for these rows you cannot tell which prompt or model produced them, and
never will — is unchanged and permanent.

**Why this matters more than a wording nit:** "zero NULL provenance" is what
you see if you check only `prompt_version`, and it reads like the problem
went away. Acting on it would have deleted a true, load-bearing caveat from a
governing document. Invariant 10 and the Landmines entry stay exactly as
written.

The single genuinely imprecise word is "NULL": for `prompt_version` the value
is now a sentinel rather than SQL NULL. That is not worth an edit to a
governing doc, and is recorded here instead.

## 2. The "24 stuck documents" are not stuck, and 9 must never be extracted

Live state:

| Source | License | Visibility | Docs | Chunks | Propositions |
|---|---|---|---|---|---|
| CLF Church | `owned` | `shown` | 15 | 247 | 0 |
| Rhemata | `owned` | `shown` | 9 | 70 | 0 |

Corpus-wide, propositions by license status:

| License | Docs | Propositions |
|---|---|---|
| `unlicensed` | 3037 | 8776 |
| `public_domain` | 547 | 2399 |
| `owned` | 24 | 0 |

Every `owned` document is at zero and no other category is — the proposition
extractor skips anything not `licensed`/`unlicensed` before it ever calls a
model. This is a gate working as designed, not a failure.

**"Stuck" was the wrong frame entirely.** Propositions feed the separate
position layer, not the chat answer path. Both sources are `owned` +
`shown`, which passes the retrieval license gate (Invariant 2) outright, so
**all 24 documents and 317 chunks are already retrievable in answers today.**
Nothing is locked out of the product.

**The 9 Rhemata documents must never be extracted.** They are the position
papers, which exist to bound answers as silent `[House Position]` context.
Extracting them would convert house doctrine into quotable teacher evidence —
precisely what Settled decision #8 forbids. If this is ever revisited, the
only candidate set is CLF Church's 15, **by explicit document ID**, never
"all documents with zero propositions" (that query also sweeps in the 2,176
permanently-excluded Precept Austin word-studies — see the standing Landmine).

Any such extraction is a database write: attended, Alex-approved, plain
script, primary session only.

## 3. The three empty teacher rows contradict nothing

| Source | License | Visibility | Docs |
|---|---|---|---|
| Bill Johnson | `unlicensed` | `shown` | 0 |
| Craig Keener | `unlicensed` | `shown` | 0 |
| Randy Clark | `unlicensed` | `hidden` | 0 |

The ingestion spreadsheet's Discovery tab marks all three
`already_in_corpus = True`, and its own Read Me defines that flag as "a source
row exists in the database" — which is true. The earlier session was not
wrong; the flag name just reads like "we have his material" when it means "we
have his name."

No user-facing effect: the Authors page renders a hardcoded list and none of
the three appear on it. The only real risk is a future ingestion pass skipping
them believing they are covered. Recorded, no work authorized.

## 4. HSTS was already present on the frontend

The 2026-08-24 scan listed missing security headers including HSTS. Vercel
already sends `strict-transport-security: max-age=63072000` on `rhemata.app`
(confirmed live). The header work shipped this session (`9b816a8`)
deliberately does **not** duplicate it — a second copy would be another value
to keep in sync. The API origin genuinely had none and now sends its own.

## Net effect

Of the five findings carried into this session, two were real and are fixed
(dependency advisories, missing security headers). Three needed no work, and
one of those three would have actively damaged the record if "fixed" as
proposed.
