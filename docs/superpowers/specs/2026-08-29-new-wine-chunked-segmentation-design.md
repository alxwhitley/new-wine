# New Wine Chunked Article Segmentation — Design Proposal

**Status:** Proposed 2026-08-29, not yet approved. No production code changed
by this document. Written per this repo's standing "architectural approval
gate" pattern (see PLAN.md Task 4.2) — implementation needs Alex's sign-off
on the design before any code lands.

## Why this exists

Task 1.1 of `docs/superpowers/plans/2026-08-28-back-to-back-completion-queue.md`
asked for one segmentation-only diagnostic call against Issue 02-1973's
cached transcript, then a classification: instruction defect, deterministic
validation defect, semantic-review defect, or irreducible model variance. The
call (2026-08-29, `openai/gpt-oss-120b`, `high` reasoning, **$0.0364**,
against the already-cached, already-OCR-passed transcript — zero new OCR
cost) rejected on `article_implausibly_long`. Inspecting the raw output
against the real transcript text and the issue's own table of
contents/page markers found the rejection trigger understated the real
defect. Alex reviewed this finding and directed scoping a chunked/windowed
redesign rather than another single-call instruction patch.

## The finding (evidence, not inference)

For roughly the back 40% of the 121,011-char transcript (from ~char 76,000
onward — inside real page ~20 of 32), the model's proposed spans and
category labels stop corresponding to the actual text at those character
offsets, even though the numbers still "tile" (contiguous coverage, no
crash, no obvious internal contradiction from the schema's point of view).
Confirmed by direct text/ToC/page-marker inspection:

- Its `"Keeping the Unity"` span `[76743:88688]` is real `"THE APOSTLE"`
  body content (the apostleship/Titus discussion, real page ~21-22).
- Its `"Christian Growth Conference advertisement"` span `[88888:93291]` is,
  word for word, the real `"Keeping the Unity"` article — confirmed by its
  own reprint byline ("Reprinted with permission: 'Keep The Unity' - New
  Adventures in Prayer..."), which the model's own `articles` list uses as
  that article's `author` field, just at the wrong offset entirely
  (`[76743:88688]`, not here).
- Its `"THE APOSTLE-GOD'S MASTER BUILDER"` span `[110353:121011]` is nowhere
  near the real title (confirmed at `62128`: `"=== PAGE 18 ===\nTHE\nAPOSTLE-\n
  GOD'S\nMASTER\nBUILDER\n\nby Derek Prince"`). The claimed range is real
  `"New Wine Forum"` reader Q&A content plus the one genuine (not
  duplicated) end-of-issue ad block (real Christian Growth Conference ad
  confirmed at page 31, offset `115873`).
- Three spans the model explicitly labeled `"(duplicate)"` are not
  duplicates — they're the single real ad occurrence, mislabeled as a copy
  of a fabricated earlier placement the model invented at `[88888:99065]`.
- Real structure, reconstructed from the issue's own table of contents
  (`"THE APOSTLE-GOD'S MASTER BUILDER" .18`, `"KEEPING THE UNITY" .24`,
  `"NEW WINE FORUM" .26`) and page markers: `"the call of love"` ends
  ~`62124`; `"THE APOSTLE"` real span is ~`[62110:88690]` (~26,580 chars,
  comfortably under the 30,000 cap on its own); `"Keeping the Unity"` real
  span is ~`[88690:93293]` (~4,600 chars); `"New Wine Forum"` real span is
  ~`[93293:115873]` (~22,580 chars, a long reader Q&A column, consistent
  with `SEGMENTATION_INSTRUCTIONS`' own description of that content shape);
  real end-of-issue ads are `[115873:121011]`, once each, not duplicated.

This is categorically different from the four defects already fixed this
week (page-marker boundary anchoring `d5420e3`, forum-content-as-ads
`4bad5b5`, foreign-title-bleed `3bc8780`, reprint/Q&A recognition
`d011fac`) — those were all mislabeling of text the model was reading
correctly at the right position. This is the model's positional/offset
grounding itself breaking down deep into one long single-shot call.
Classified: **model scaling limit** (variance inherent to the current
single-call, whole-121K-char architecture), not an instruction gap — no
instruction wording tells the model where character 88,690 is; that has to
come from the model's own internal tracking across a ~30K-token input, and
that tracking is what's failing here.

## Why chunking should help

- Every confirmed positional failure sits deep into the transcript (>60%
  through a single ~30K-token call). Everything the model got right in the
  same run — correctly finding `"Health and Healing"`, `"Editorial"`,
  `"The Nature of Obedience"`, `"BIBLE STUDY"`, and even the real page-18
  `"THE APOSTLE"` title text being present and legible in the transcript —
  sits earlier in the document.
- Bounding how much transcript the model must track positionally in one
  call is the direct lever against a distance-dependent grounding failure.
  This doesn't need better instructions; it needs giving the model less to
  lose track of at once.
- Page markers (`=== PAGE N ===`) are exact, already verified by the OCR
  completeness-review stage, and free to locate deterministically (a Python
  regex or the already-parsed `VerifiedTranscriptPage.transcript_start/
  transcript_end`) — no model call needed to find them. This makes
  page-anchored windowing safe as a chunking boundary: nothing about where
  a window starts or ends is something the model has to compute.

## Proposed design

### Windowing

Split `VerifiedIssueTranscript` into overlapping windows of consecutive
**pages** (never arbitrary char offsets, which would risk chopping
mid-word/mid-sentence and adding a second, self-inflicted grounding
problem), using the already-verified per-page offsets — pure Python, zero
cost, zero model risk. Window N covers pages `[a, b]`; window N+1 covers
pages `[b-overlap, c]`. Overlap must comfortably exceed the longest
confirmed-legitimate article seen so far (26,580 chars / ~6 pages, "THE
APOSTLE") so a full article is very likely to sit entirely inside at least
one window even when it straddles a window seam.

### Per-window segmentation call

- Same `SEGMENTATION_INSTRUCTIONS`, same model and reasoning effort, scoped
  to one window's text, with window-relative (not global) offsets.
- Add two boolean fields to the article schema for this call only:
  `continues_from_before` (this window's first proposed article actually
  started earlier, outside this window) and `continues_after` (this
  window's last proposed article actually continues past this window). This
  lets the model say "I can't see the true boundary here" instead of
  guessing one.
- Reuse the existing per-window coverage/overlap/size-cap checks, scoped to
  that window's own text length rather than the whole issue.

### Deterministic merge (no model call)

- Translate every window-relative offset to a global transcript offset
  using that window's own first-page `transcript_start` — arithmetic only,
  so this step cannot itself introduce a new positional-grounding failure.
- In each overlap region between adjacent windows, reconcile: if window N's
  `continues_after` article and window N+1's `continues_from_before`
  article agree (normalized title/author match — the same normalization
  rule the existing title-bleed check already uses), merge them into one
  article spanning the min-start/max-end. If they disagree, or a window's
  "complete" article is contradicted by its neighbor's proposal over the
  same text, **fail closed** — this is a quarantine-or-repair case (open
  question 2 below), never a silent pick.
- Run the **existing, unmodified** deterministic validation (coverage,
  overlap, `_MAX_ARTICLE_CHARS`, `_OTHER_NON_ARTICLE_MAX_CHARS`/
  `_NAMED_NON_ARTICLE_MAX_CHARS`, `_NON_ARTICLE_TOTAL_FRACTION_MAX`,
  `_TITLE_BLEED_WINDOW_CHARS`) against the merged, whole-issue candidate —
  none of these checks need to change; they already operate on one
  (articles, non_article_spans) set regardless of how many calls produced
  it.

### What stays exactly the same

- `review_articles_against_issue()` — one whole-issue, fresh-context
  semantic review pass over the merged article set, unchanged. Today's
  finding doesn't implicate this stage's own accuracy (it never even ran;
  segmentation failed deterministic validation first), and it doesn't carry
  the same global-offset-counting burden segmentation does — it judges each
  article's own narrative coherence, not where every character sits.
- `ArticleManifest`/`ArticleRecord`, the `write_artifact` identity/hash-chain
  discipline, and every existing deterministic cap and its documented
  reasoning.
- Proposition extraction and everything downstream, unchanged.

## Open questions requiring Alex's decision before implementation

1. **Window size / overlap.** Needs live calibration against real evidence,
   not a guessed number — same "reasoned starting point, not a calibrated
   constant" posture as `DOMINANCE_THRESHOLD` (Invariant 20). Starting
   proposal to calibrate from: 10-page windows / 3-page overlap (roughly
   35-40K chars per window) — comfortably inside the zone this session's
   evidence still shows as reliable, but unverified until tested.
2. **Boundary-conflict handling.** When two adjacent windows disagree about
   a straddling article, does the whole issue quarantine immediately
   (matching the standing "one failed page/article/proposition quarantines
   everything" posture, Invariant 17), or does it get one bounded
   automatic repair pass first (matching the existing OCR page-repair
   precedent — re-run just the two conflicting windows with the specific
   disagreement named)? This is a real product-posture call, not a default
   I should pick unilaterally.
3. **Cost.** More, smaller calls instead of one large one. Today's single
   whole-issue call cost $0.0364. A first-pass, unverified estimate: 4
   windows at roughly a third of the input size each ≈ $0.06-0.10 total for
   segmentation — comfortably inside the existing $1.25 per-issue ceiling
   and the $50 corpus-wide rule, but this needs a real measured number
   before anyone relies on it.
4. **Does chunking need to touch OCR completeness review too?** No evidence
   from today's finding says so — OCR passed cleanly (32/32 pages) before
   segmentation ran. Out of scope unless new evidence says otherwise.

## Non-goals

- No code changes in this pass — design only.
- No new live/paid calls beyond the one already spent ($0.0364) diagnosing
  today's finding.
- Does not touch OCR, proposition extraction, or the semantic review stage's
  own logic.
- Does not authorize a production database write, source-file promotion, or
  file move (unchanged from this queue's Packet 1 non-goals and Invariant
  17).

## Suggested next step (pending Alex's approval)

A bounded, named-cost live calibration: implement the windowing/merge layer
above, run it against Issue 02-1973's cached transcript, and compare its
merged output directly against the ground-truth positions this session
hand-verified (listed under "The finding," anchored to the issue's own
table of contents and page markers) before touching `articles.py`'s
production call path.
