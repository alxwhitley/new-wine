# A1 — Beta corpus manifest: live census (read-only)

**Date:** 2026-08-19. **Connection:** `rhemata_readonly_analysis` role via
`backend/app/.env.readonly-analysis` (write-rejection confirmed live —
a test `UPDATE` on `documents` raised `ReadOnlySqlTransaction` before any
real query ran). No write of any kind was issued against the database.

**Scope of this document:** raw current numbers only, for docs/roadmap.md's
A1 and the Private-beta convergence gate's "live census" requirement. This
does **not** propose a minimum-coverage bar — that's Alex's call per A1's
own text. Treat every number below as a dated snapshot, not a durable fact
— per CLAUDE.md's standing rule, re-query before trusting later.

---

## Corpus totals

| Metric | Count |
|---|---|
| Sources (teachers/works) | 76 |
| Documents | 3,608 |
| Chunks | 185,508 |
| Propositions (total) | 11,175 |
| Propositions (`eligible=true`) | 8,297 |
| Quotes (total, incl. revoked) | 823 |
| Quotes `approved` | 664 |
| Quotes `pending` | 157 |
| Quotes `revoked` | 2 |
| Quotes on new gold pipeline (`quality_pipeline_version='quote_quality_v1'`, `selection_eligible=true`) | 28 |
| Quotes legacy/unserved (`quality_pipeline_version IS NULL`, `selection_eligible=false`) | 795 |

## Sources by license_status × visibility

| license_status | visibility | count |
|---|---|---|
| owned | shown | 2 |
| public_domain | hidden | 2 |
| public_domain | shown | 28 |
| unlicensed | hidden | 11 |
| unlicensed | shown | 33 |

**13 sources are not `visibility='shown'`:** Jesus Image, Kathryn Kuhlman,
Keith Green, Mark Virkler, Paris Reidhead, R.T. Kendall, Randy Clark, Robert
Trail, Roberts Liardon, Sam Storms, T. Austin-Sparks, Thomas Brooks, and the
sentinel "Unassigned — needs source" row (CLAUDE.md Invariant 3 — correct
by design, never meant to be visible). Of these, only Robert Trail and
Thomas Brooks have any documents/chunks at all (1 doc each); the rest have
zero documents — they are name-only source rows with no ingested content.

## Documents by source_kind / source_type

| source_kind | source_type | count |
|---|---|---|
| word_study | background | 2,176 |
| sermon_transcript | sermon | 821 |
| commentary | commentary | 493 |
| book | book | 53 |
| magazine_article | magazine_article | 33 |
| paper | paper | 10 |
| position_paper | position_paper | 9 |
| lexicon | background | 4 |
| web_article | article | 4 |
| sermon_transcript | other | 2 |
| sermon_transcript | manual | 1 |
| unknown | book | 1 |
| book | other | 1 |

`word_study` (Precept Austin, 2,176 docs) and `commentary` (493 docs) are
hard-excluded from answer generation per CLAUDE.md's commentary-exclusion
and Precept-Austin landmines — searchable only, never answer evidence.

## Per-teacher breakdown (sources with any documents, sorted by eligible propositions)

| Teacher/source | license | visibility | docs | chunks | props eligible | props ineligible | quotes approved | quotes selection-eligible | quotes total |
|---|---|---|---|---|---|---|---|---|---|
| Derek Prince | unlicensed | shown | 496 | 11,062 | 3,538 | 1,640 | 663 | 28 | 820 |
| John Wesley | public_domain | shown | 2 | 2,887 | 1,158 | 91 | 0 | 0 | 0 |
| Vlad Savchuk | unlicensed | shown | 126 | 1,678 | 982 | 146 | 0 | 0 | 0 |
| Leonard Ravenhill | unlicensed | shown | 117 | 1,259 | 767 | 51 | 0 | 0 | 0 |
| Andrew Murray | public_domain | shown | 10 | 1,352 | 611 | 287 | 1 | 0 | 3 |
| Zac Poonen | unlicensed | shown | 50 | 759 | 411 | 52 | 0 | 0 | 0 |
| Doug Kreighbaum | unlicensed | shown | 9 | 914 | 199 | 251 | 0 | 0 | 0 |
| New Wine Magazine | unlicensed | shown | 15 | 97 | 112 | 37 | 0 | 0 | 0 |
| Brother Lawrence | public_domain | shown | 1 | 43 | 104 | 17 | 0 | 0 | 0 |
| E.M. Bounds | public_domain | shown | 7 | 821 | 103 | 28 | 0 | 0 | 0 |
| Daniel Kolenda | unlicensed | shown | 11 | 218 | 53 | 31 | 0 | 0 | 0 |
| F.F. Bosworth | unlicensed | shown | 1 | 256 | 49 | 113 | 0 | 0 | 0 |
| Carter Conlon | unlicensed | shown | 6 | 86 | 41 | 7 | 0 | 0 | 0 |
| Bob Mumford | unlicensed | shown | 4 | 43 | 36 | 13 | 0 | 0 | 0 |
| Jack Deere | unlicensed | shown | 6 | 143 | 23 | 8 | 0 | 0 | 0 |
| Charles Simpson | unlicensed | shown | 4 | 41 | 16 | 15 | 0 | 0 | 0 |
| Vlad Savchuk (web staging) | unlicensed | shown | 4 | 15 | 16 | 20 | 0 | 0 | 0 |
| Covenant Harvest Church | unlicensed | shown | 1 | 93 | 15 | 21 | 0 | 0 | 0 |
| Ern Baxter | unlicensed | shown | 2 | 28 | 12 | 14 | 0 | 0 | 0 |
| Don Basham | unlicensed | shown | 2 | 21 | 10 | 6 | 0 | 0 | 0 |
| Michael Brown | unlicensed | shown | 2 | 14 | 10 | 2 | 0 | 0 | 0 |
| Oswald J. Smith | unlicensed | shown | 1 | 8 | 8 | 0 | 0 | 0 | 0 |
| Ruth Prince | unlicensed | shown | 2 | 51 | 0 | 0 | 0 | 0 | 0 |
| *Unassigned — needs source* | unlicensed | **hidden** (sentinel) | 2 | 34 | 4 | 28 | 0 | 0 | 0 |

**Zero-documents-with-content sources** (name registered, nothing ingested):
A.W. Tozer, Andrew Wommack, Art Katz, Bill Johnson, Christian Classics
Ethereal Library, Craig Keener, David Pawson, David Wilkerson, Duncan
Campbell, Frank Bartleman, Gabriel Heights, Jesus Image, John Bevere,
Kathryn Kuhlman, Keith Green, Mark Virkler, Paris Reidhead, Prophetic
Equipping, R.T. Kendall, Randy Clark, Roberts Liardon, Sam Storms, Smith
Wigglesworth, T. Austin-Sparks. (Cross-checked against the master
ingestion-candidate spreadsheet from the prior session: Bill Johnson, Randy
Clark, Daniel Kolenda, Craig Keener appeared there as "already in corpus" —
Daniel Kolenda has real content [11 docs, 53 eligible props]; Bill Johnson,
Randy Clark, and Craig Keener are name-only rows with zero documents, which
is a narrower state than "already in corpus" implies.)

**Sources with documents but zero eligible propositions** (27 rows — mostly
reference/commentary material excluded from answers by design, but some are
genuine teacher voices with content ingested and no propositions extracted):
A.B. Bruce, A.J. Gordon, Abraham Kuyper, Adam Clarke, An Unknown Christian,
Catherine Booth, Chapel Library, Charles G. Finney, **CLF Church** (owned,
15 docs/247 chunks, 0 propositions), F.B. Meyer, George Müller, Hannah
Whitall Smith, HistoricalChristianFaith Commentaries Database, J.C. Ryle,
J.R. Miller, Jamieson Fausset & Brown, John Owen, Jonathan Edwards, Matthew
Henry, Phoebe Palmer, Precept Austin, R.A. Torrey, **Rhemata** (owned, 9
docs/70 chunks, 0 propositions), Robert Trail (hidden), Samuel Dickey
Gordon, STEPBible, Thomas Brooks (hidden), William Booth.

Not interpreted here whether zero-proposition status blocks these sources
from appearing in answers — the main producer.py retrieval path was not
traced in this pass; propositions are confirmed load-bearing only for
position-generation (Invariant 12) and quote extraction. Flagging the two
**owned** rows (CLF Church, Rhemata) specifically since those are Alex's
own first-party content with zero propositions, which is more likely to
matter for a coverage decision than the reference/commentary rows.

## Retrievability sanity check

Checked every source with `props_eligible > 0` against its own
`visibility` value (not a sample — all 24 such rows, since the query
returned few enough to check exhaustively). **Only one row has eligible
propositions while not `visibility='shown'`:** the "Unassigned — needs
source" sentinel (4 eligible propositions, `hidden`) — this is Invariant
3's intended state, not a gap; the sentinel is never meant to be
retrievable. **No real named teacher has eligible propositions sitting
behind a hidden/unshown source.** No retrievability gap of the kind the
convergence gate is checking for was found.

## Quote concentration (confirms CLAUDE.md Settled #28's documented figure)

Only two sources have any quotes at all: **Derek Prince** (820 quotes total,
663 approved, 28 on the new gold `quote_quality_v1` pipeline) and
**Andrew Murray** (3 quotes total, 1 approved, 0 gold-pipeline/selection-
eligible). All 823 quotes corpus-wide belong to just these two sources —
consistent with, and reconfirms live, the "793 of 794 are Prince's" figure
already on record in CLAUDE.md Settled #28 (the small count difference is
the 28 new gold-pipeline rows added since that figure was recorded, plus 2
revoked). "Vlad Savchuk (web staging)" (4 docs, 16 eligible propositions)
has zero quotes yet — consistent with PLAN.md W9's own description of that
work as write/eligibility/shown only, quote extraction not yet run there.

## Not covered by this pass

- No proposal for what A1's minimum teacher/source/content-shape coverage
  bar should be — that's explicitly Alex's decision per A1's own text.
- No cost/storage estimate.
- No sampling or quality review of any content — counts only.
- Did not trace whether producer.py's retrieval path depends on
  propositions existing, or only on chunks — relevant to interpreting the
  "27 sources with docs but 0 eligible propositions" list correctly, left
  for whoever picks up A1 for real.
