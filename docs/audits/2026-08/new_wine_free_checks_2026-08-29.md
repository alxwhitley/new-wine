# New Wine A2 — Free-Check Protocol Results, 2026-08-29

**No live model calls.** Every check below runs against already-extracted data:
the real 121,011-char verified transcript for Issue 02-1973 (recovered from
`docs/audits/2026-08/new_wine_issue_02_1973_review_2026-08-27_v6/article_manifest.json`,
`payload.transcript` — confirmed byte-length-identical to the known figure)
and that same run's `article_manifest.json`, the one historical run this
session whose `gate_results.articles` was `True`. This is the "free-check
protocol" from the Grok patch-set exchange earlier today (chunking and
ToC-anchored designs both refuted; patch set addressed the two remaining
gaps — folio-mapping gate, marker-exclusion gate — plus recalibrated model
language and a cost model). Run before spending anything on a live Layer
1+2 test, per that patch set's own gate.

## 1. Marker intervals

32 `=== PAGE N ===` markers found, zero overlaps, `n` strictly increasing
1–32. **Correction to the patch set's own framing**: `marker_n` is not
something that needs fuzzy resolution — `scripts/magazine_review/transcript.py::canonical_verified_transcript()`
inserts these markers by enumerating `(page_number, page_text)` pairs in
order, so `marker_n` **is** the PDF page index by construction, always
clean, never OCR'd. The only real fuzzy-matching problem is the join from
`marker_n`/PDF-index to the *printed* folio (the number scanned off the
physical page) — a single join, not two.

## 2. Marker-exclusion predicate

Tested against `new_wine_issue_02_1973_review_2026-08-27_v6`'s single
article (`article-1`, `transcript_start=0`, `transcript_end=121011`,
`text` byte-identical to the full transcript — this is a live instance of
the CLAUDE.md Landmines-documented "single article spanning the whole
issue" defect). **All 32/32 markers intersect its span.** This real
historical run passed the OLD article gate (`gate_results.articles: True`)
despite being total nonsense. The proposed marker-exclusion gate would
have correctly rejected it.

## 3. Folio map

Footer-region regex search (last 400 chars of each page body) against six
observed footer formats (`**NEW WINE** / **N**`, `N / FEBRUARY 1973`,
`NEW WINE / N`, `FEBRUARY 1973 / N`, bare trailing `N`):

- **25/32 resolved, 0/25 mismatched** against `marker_n`. Zero exceptions
  to `folio_printed == marker_n` (offset 0) across every resolvable page —
  strong empirical support for this issue using a flat, unshifted
  pagination.
- **7/32 unresolved**: pages 1, 4, 16, 17, 18, 24, 32. Checked each by hand
  (not just a regex miss) — all are genuine absences: page 1 is the cover/
  teaser (no footer), page 18 is a 76-char title splash for "The Apostle"
  (cuts off mid-word, no footer reached), page 24 is the 9-word "Keeping
  the Unity" reprint-credit block, page 32 is back-cover ad copy, page 16
  ends mid-genealogy-table with no trailing folio, page 17 ends on an
  unattributed poem, page 4 (a letters page) has no visible footer in the
  captured tail. None contradict the offset-0 finding — they're absent,
  not mismatched.

## 4. TOC listed pages vs. folio map

Real table of contents recovered at transcript offset ~13,241 (page 5),
matching (and refining) the offset the earlier refuted docs cited:

| Title | Author (as printed) | Listed page |
|---|---|---|
| HEALTH AND HEALING-IT'S UP TO YOU! | Derek Prince | 2 |
| THE NATURE OF OBEDIENCE | Bob Mumford | 9 |
| BIBLE STUDY | Howard Coffey | 15 |
| THE CALL OF LOVE | Lea Kriebs | 17 |
| THE APOSTLE-GOD'S MASTER BUILDER | Derek Prince | 18 |
| KEEPING THE UNITY | *(none listed)* | 24 |
| NEW WINE FORUM | *Spiritual Potpourri* (subtitle, not author) | 26 |

Joining against Check 3's folio map: **4/7 rows (2, 9, 15, 26) resolve with
independent per-page folio confirmation. 3/7 rows (17, 18, 24) land in the
unresolved set** — meaning a strict, per-page-only reading of the patch
set's mapping gate ("any TOC listed_start_page does not resolve to exactly
one `mapping_status: ok` marker" → reject) would **quarantine 3 of 7 real
articles in this issue**, including the two hardest, most failure-prone
cases already known from prior sessions (the interrupted "Apostle" article
and the reprint with no listed author).

The patch set's own escape hatch — "a single global offset is allowed only
if it holds for every resolvable folio in the issue" — is what rescues
this, and Check 3's zero-mismatch result is exactly the evidence needed to
invoke it safely here. **This is load-bearing, not decorative — but it's
underspecified**: the patch text doesn't say how many resolved points are
required before trusting a global offset, or what counts as "consecutive."
Needs a concrete minimum-sample-size rule before this is implementable,
not just the one-paragraph description as written.

## 5. Jump-line detector vs. real text

One real hit in the entire 121,011-char transcript: `"*(Continued on page
6)*"` at offset 7,674, on page 3, correctly flagging the real "Health and
Healing" interruption (pages 2–3, resumes 6–8, per prior sessions'
findings). **Zero false positives** — no header junk, no subscription-form
noise, nothing spurious matched the phrase list across the whole issue.

**Real gap, not previously named**: page 6 (the resumption point) carries
no matching "continued from" phrase — checked directly, nothing in its
opening text references the interruption. The detector only catches the
*departure* half of a stitch. Locating exactly where the resumption span
starts still depends on marker-boundary + non-article-classification
logic, not the jump-line phrase alone — Layer 4's "stitch discontinuities
when jump links / page hints say so" needs a real rule for this, not an
implicit one.

## 6. Coverage arithmetic

The OLD "totals add up" check (`sum(article spans) == transcript_length`)
is foolable exactly as suspected: `article-1`'s span alone covers
121,011 characters, matching `transcript_length` exactly, while fully
containing all 32 marker intervals (not disjoint from them). A
partition-correct check —
`sum(article) + sum(non_article) + sum(markers) == transcript_length`,
requiring disjointness — correctly flags this: `121,011 + 0 + 503 =
121,514 ≠ 121,011`. The 503-character discrepancy is exactly the marker
text swallowed into the article body. Confirms the old check's blind spot
concretely, on real data.

## 7. Author-list fixtures (no model)

Hand-filled JSON against the patch set's schema for the three known
landmine cases, all validate without schema changes:

- **New Wine Forum panel** (confirmed via a real inline speaker label,
  `"Basham - Since we live in an age..."`, offset ~94,200): `kind: panel`,
  four `authors[]` rows (Mumford, Prince, Simpson, Basham) each
  `role: panelist`, `confidence: inferred_from_speaker_labels`,
  `attribution_policy: do_not_project_propositions_to_a_single_person`.
  Confirms "Spiritual Potpourri" never has to appear as an author name —
  it's correctly excluded as a subtitle.
- **Keeping the Unity reprint** (full text checked, pages 24–25 — no
  individual person named anywhere in the ToC or the body, only "Reprinted
  with permission... New Adventures in Prayer, Prayer Group Newsletter"):
  `kind: reprint`, one `authors[]` row, `role: original_source`,
  `name: "New Adventures in Prayer (Prayer Group Newsletter)"`. Validates,
  but surfaces a real downstream question the patch set doesn't address:
  Invariant 7 (`CLAUDE.md`) requires `citation_mode: citable` to attach to
  "a real attributable NAME" — a credited publication, not a person, is an
  open question for whether that downstream rule treats it as citable.
- **Unsigned page-5 editorial** (no ToC entry at all — a real orphan-sweep
  case): `authors: []`. **Minor schema ambiguity found**: the schema's
  `kind` enum has both `editorial` and `unsigned` as distinct values, and
  nothing states which one an unsigned editorial column should carry, or
  whether `authors: []` is valid under `kind: editorial` as well as
  `kind: unsigned` (the patch text only explicitly blesses the
  `unsigned`+empty-array combination).

## Bottom line

All 7 checks ran clean, on real data, at zero cost. Findings 4 and 5 add
genuine detail the patch set didn't have (the global-offset escape hatch
is necessary and empirically supported here, but underspecified; the
jump-line detector needs a resumption-point rule beyond phrase-matching).
Nothing here contradicts the patch set's direction — no live spend
authorized by this document. Per the patch set's own bar, still
outstanding before a live Layer 1+2 test: the cost table needs real
article/jump-line counts from at least 2 more transcripts (only this one
was checked here), and the `usage` breakdown behind the $1.4776 figure
still needs to be pulled from wherever it was actually logged, if it was.
