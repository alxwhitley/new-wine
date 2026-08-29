# New Wine A2 Segmentation — v2 Proposal, Refuted

**Status:** This was drafted 2026-08-29 as a second design proposal (v1, the
chunking design, was refuted the same day — see
`2026-08-29-new-wine-chunked-segmentation-design.md`). It was adversarially
reviewed before being shown to Alex, and the review's core findings were
independently reverified directly against the repo and the real transcripts
rather than accepted on trust. They held up. **This design is also refuted.
Do not implement from it.** Kept at this path, not deleted, so the pattern
across all three attempts this session is visible rather than erased.

## What v2 tried to fix

v1 (chunking) was refuted for stating two false claims as fact (grounding
degrades late in a document; spans tile without contradiction). v2 tried to
apply more discipline — every claim tagged `[VERIFIED]`, `[PRECEDENT]`, or
`[PROPOSED]` — and proposed anchoring articles to the table of contents,
requiring authorship claims to carry an exact, offset-checkable evidence
span (mirroring the existing proposition-evidence and quote-verifier
patterns) rather than trusting a bare model assertion.

## Why it's refuted anyway

The added discipline didn't survive contact with adversarial review — several
things marked `[VERIFIED]` were inferences, and the mechanism had at least
one internal self-contradiction. All of the following were independently
reverified directly against the repo/transcripts after review, not accepted
on the reviewer's word:

1. **A `[VERIFIED]`-labeled claim was false.** The doc asserted Issue 02-1980
   has no parseable table of contents ("confirmed real case: `02-1980`",
   inherited from the v1 findings doc without re-checking it). Direct read
   of `02-1980`'s raw transcript shows a real ToC in a *seventh* distinct
   format: `"3. REDISCOVERING PRAYER\nby Don Basham"`, numbered by printed
   page, with the byline inline — actually a *better*-structured ToC than
   Issue 02-1973's, not a missing one. This is the exact mistake v2 existed
   to avoid, made once inside the document meant to prevent it.
2. **The proposed deterministic "article-end" marker is genuinely ambiguous
   in the same issue it was drawn from.** v2 proposed detecting the `☐`
   pilcrow as a hand-off point closing an article span. Direct search of
   Issue 02-1973's own OCR cache finds `☐` used identically as a literal
   subscription-form checkbox (`"☐ Please check here to enter new
   subscription..."`, four+ occurrences) as well as an article-ending mark.
   A rule built on this glyph alone would false-positive on a subscription
   form.
3. **The discontiguous-span schema change has no algorithm that would ever
   produce more than one span.** v2 proposed `spans: tuple[(start, end),
   ...]` to represent an article interrupted by other material, but its own
   span-establishment rule two sections later is unchanged from the refuted
   v1 design: "ToC-anchored spans stop at the next article's start." Under
   that rule there is no mechanism that ever emits a second span for one
   article — the exact case that motivated the requirement (Health and
   Healing, interrupted pages 4–5) would still be silently swallowed whole.
4. **A load-bearing, untagged factual claim about the code was wrong.** The
   doc stated the `text` field on `ArticleRecord` is "already a derived
   property, would concatenate" — asserted as settled fact, not tagged
   `[PROPOSED]`. It is a plain dataclass field
   (`scripts/magazine_review/schemas.py`), set once from one contiguous
   transcript slice (`articles.py:771`), then hashed. Under genuinely
   discontiguous spans, a proposition's evidence-offset round-trip check
   (`proposition_review.py`) could validate against a seam that never
   existed contiguously in the real transcript — undermining the exact
   integrity property that check exists to guarantee.
5. **The proposed mechanism doesn't implement the requirement it claims
   lineage from.** The v1 findings doc required authorship checks to compare
   the printed byline against the ToC and hard-refuse on disagreement. v2's
   evidence-grounding mechanism only checks a claimed author against
   evidence *inside the article's own text* — it never reads or compares the
   ToC's claim at all.
6. **It contradicts already-shipped, live code.** `SEGMENTATION_INSTRUCTIONS`
   in `articles.py` (added `d011fac`, 2026-08-27, still live) explicitly
   tells the model that for a Forum-style Q&A column it should use *"the
   column's own name, or 'Readers' if none is given,"* as the author — a
   synthesized label that, by construction, will never appear in the
   transcript as a named person. Under v2's own evidence-grounding rule, this
   existing, currently-deployed instruction would systematically fail the
   new check it introduces. The document never reconciles the two.
7. **No cost figure appears anywhere against the stated ceilings.** $1.25/
   issue and $50/corpus-run are named constraints in the contract; the
   document never estimates the proposed pipeline's cost against them.
8. **The recommended scope (Option A: quarantine multi-speaker articles)
   directly drops a requirement the document opens by claiming to satisfy**
   ("multi-author articles are first-class") — disclosed in the document, not
   hidden, but with no estimate of how much of the 167-issue backlog contains
   Forum-style panel content and would therefore never clear the gate.
9. Lower-severity: the folio↔PDF-page verification sketch checks for
   monotonic increase, which would not catch a constant additive offset (the
   specific failure v1's findings named); a real OCR disagreement on a byline
   exists in the corpus itself with no fuzzy-matching discussion; and the
   document's own "~50 chars" byline-proximity figure understated the real
   spread when checked at broader sample size (up to 164 chars, 20% no-match
   within 300 chars).

**One thing did hold up under review**, worth keeping separate from the
above: every specific file/line citation in the document (`articles.py:766`,
`:810-824`, `:874`, `proposition_review.py:507`, `ingest_magazine.py:353/
407/412`) was checked directly and was accurate. The rigor was real where it
was applied — it just wasn't applied evenly across the whole document, and
the errors are concentrated in exactly the claims presented with the most
confidence.

## What survives across all three attempts today

- Derive article offsets deterministically from verified page markers —
  never from model-emitted offsets (v1's one surviving principle).
- Require an exact, offset-checkable evidence span behind any non-
  deterministic claim (authorship, category) rather than trusting a bare
  model assertion — this pattern is precedented elsewhere in the codebase
  (proposition evidence round-trip, quote-verifier exact-substring check)
  and nothing in today's review refuted the *pattern*, only this specific,
  underspecified application of it.
- `author: str` cannot represent this corpus's real content (multi-speaker
  panels exist and are a recurring feature, not an edge case) — confirmed
  independently by both the schema read and the live transcript evidence.
  Whatever design eventually gets built has to make a real, deliberate
  decision about multi-speaker attribution, not default around it.
- ToC format is not stable enough to hand-write a single parser against —
  **seven** distinct formats now confirmed across seven issues examined
  (table-of-title-author-page, numbered-with-inline-byline, page-number-only
  columns, and at least one issue with no ToC-detectable-by-simple-string-
  match despite genuinely having one).

## Honest note on the pattern this session

Three architecture proposals were written with confident, specific claims
today (`15f6b1d` chunking, this file's original v2 content, plus the
authorship mechanism inside it). All three were adversarially reviewed. All
three failed review on claims that were checkable and wrong, not on
judgment calls. This is recorded here rather than smoothed over because a
fourth attempt using the same process (write confidently, verify after) would
likely fail the same way. A real design for this problem needs either a
different process (verify each individual mechanism live, in isolation,
before composing them into a document) or a session structured around
smaller, individually-tested pieces rather than one comprehensive proposal.

## Non-goals

- No code changes.
- No new live/paid calls beyond the $0.0364 already spent earlier the same
  day (v1's diagnostic call). All verification for v2 used already-extracted,
  free transcript data.
- Does not authorize a production database write, source-file promotion, or
  file move.
