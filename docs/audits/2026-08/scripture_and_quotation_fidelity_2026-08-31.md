# Scripture and quotation fidelity in served answer prose — 2026-08-31

**Type:** read-only audit. Zero database writes, zero LLM spend, zero
production changes. All SELECTs run through `SUPABASE_DB_URL` (psycopg2,
`set_session(readonly=True)`).

**Why now:** a parallel session is working on increasing the biblical depth of
answers. Depth means more Scripture and more source wording in the prose
channel. This audit measures what guards that channel today, before the
change lands.

**Corpus of evidence:** the 5 complete answers already stored in
`scripts/sp1_answer_quality_baseline.json`. Nothing was generated for this
audit.

**Stop condition:** the three questions below are answered with named
evidence. Adjacent findings are recorded, not investigated.

---

## Summary

The reference verifier does exactly what it was designed to do and nothing
more. `reference_verifier.verify_verse_mention()` is a **pointer** check: it
confirms a cited verse exists as a row in `verses`. It does not compare the
answer's claim, or the answer's quoted wording, against the verse text. There
is no equivalent check anywhere for teacher wording in prose.

Three findings, in severity order.

| # | Finding | Severity |
|---|---|---|
| 1 | A fabricated quotation attributed to a living minister, plus a nested-attribution error and an altered quotation, all in the prose channel | Ranked failure mode #2 |
| 2 | Scripture quoted with no reference at all — structurally outside every guard | Ranked failure mode #1 surface |
| 3 | Scripture quotations don't match the app's own verse text, so citation click-through disagrees with the answer | Product-quality |

---

## Finding 1 — The prose channel emits verbatim quotations, and 3 of 7 are defective

`backend/app/system_prompt.txt:158` reads:

> Never reproduce quotes or lift phrasing verbatim, in any mode. Paraphrase
> with attribution.

The baseline answers violate this 7 times, with explicit verbatim-attribution
language ("In his words", "As Kolenda points out", "Prince warns that"). Each
was checked against the live corpus by exact substring.

| Quotation | Attributed to | Corpus check | Verdict |
|---|---|---|---|
| "It's not something weird… weekly life of the church" | Kolenda | HIT, but the source continues "**that I pastor**" | truncated |
| "what brought success in the '60s brings death in the '70s" | Prince | HIT | clean |
| "What should we do at this time?" | Prince | HIT | clean |
| "the most common sign of the baptism of the Spirit" | Brown | HIT, Brown's own words | clean |
| **"one who declares something not his own"** | **Kolenda** | **0 chunks corpus-wide** | **fabricated** |
| "one who has supernatural knowledge" | Kolenda | HIT — but the words are **Wayne Grudem's**, quoted by Kolenda | misattributed |
| "piping fresh oil into the lampstand" | Prince | real text is "to **pipe the** fresh oil into the lampstand" | altered |

**4 of 7 defective (57%).**

The truncation was found on the second pass, while building the guard — the
first pass scored it clean against a fixture that was itself truncated. The
source reads "…part of the normal, ongoing, weekly life of the church **that I
pastor**." The answer closes the quotation one clause early with a period the
source does not have, converting Kolenda's statement about his own local
congregation into one about the church universal. Settled decision #16 names
this exact hazard — "NO words trimmed at either end… a trim can reverse
meaning while passing every check" — but it was written about the quote rail.
Nothing was watching the prose channel.

The fabrication is the serious one. The answer reads:

> As Kolenda points out, it often meant simply "one who has supernatural
> knowledge" or "one who declares something not his own" — not automatically
> one who speaks with absolute divine authority.

The real chunk (`Daniel Kolenda — Cessationism 3 (Has Prophecy Ceased?)`) is
Kolenda **quoting Wayne Grudem's book**:

> He says, "By the time of the New Testament, the term *prophetes* in everyday
> use often simply meant one who has supernatural knowledge, or one who
> predicts the future, or even just spokesman without any connotations of
> divine authority."

So the first quoted phrase is Grudem's, re-credited to Kolenda; the second
phrase — `"one who declares something not his own"` — does not exist anywhere
in the corpus (`SELECT count(*) FROM chunks WHERE content ILIKE '%declares
something not his own%'` → **0**; the looser `'%something not his own%'` → **0**).
Daniel Kolenda is a living minister.

The Prince case is milder but the same shape: the corpus has Prince saying
"the function that Don and I have **in this conference** is to pipe the fresh
oil into the lampstand," immediately followed by his own hedge — "If you want
to say that's the prophetic ministry, I will not say no." The answer strips
the conference context and the hedge and presents the phrase as his
definition of the prophetic ministry. `'%piping fresh oil%'` → **0**
corpus-wide.

**Why no guard caught this.** `reference_verifier.verify_teacher_mention()`
grounds the *name* — it confirms Kolenda's material was actually retrieved for
this question, which it was. Nothing checks the *wording* attributed to that
name. The quote rail's authenticity machinery (`quote_verifier.py`'s exact
substring match, provenance, boundary checks) governs the **verified-quote
component only**; this text came out of the prose channel. `QUOTE_SELECTION_
ENABLED=false` does not contain it — Settled #30 turned off the rail, not the
model's ability to type quotation marks.

This is the exact control Settled decision #17 names as required and treats as
supporting the enforceable quote claim:

> the prose channel must be prevented from rendering quotation typography and
> verbatim-attribution language

That prevention is currently one line of prompt text, and it is not holding.

---

## Finding 2 — Scripture quoted with no reference at all

Two of the 19 quoted spans in the baseline are Scripture carrying no reference
anywhere near them:

- `"prophesy who hit you,"` — Matthew 26:68 / Luke 22:64
- `"all prophesy, one by one,"` — 1 Corinthians 14:31

`reference_verifier` only ever sees what the model declares in its
`<reference_mentions>` block, and guard 1 (presence) is a literal substring
search for the declared reference string. Scripture that is quoted but never
declared is invisible to every guard, produces no citation link, and gives the
reader nothing to click through and check.

`system_prompt.txt:160` is the mechanism:

> Scripture exception: You may cite Scripture directly from your training
> knowledge to ground what the retrieved sources are already saying… Only cite
> scripture you are certain of — if uncertain, paraphrase rather than quote.

Scripture in answers comes from training knowledge, not from the `verses`
table the app itself serves. "Only cite scripture you are certain of" is a
self-assessment instruction, and Settled decision #8 already records the
standing objection to that shape — the system self-assessing doubt is
unreliable, and skips the check exactly when it matters most.

---

## Finding 3 — Quoted Scripture doesn't match the app's own verse text

14 compact `Book C:V` references appear across the 5 answers. **All 14 resolve**
— `verify_verse_mention()` would pass every one, and every claim attached to
them is defensible. There are no fabricated verse pointers here.

But 5 of the 14 are rendered as **direct quotations**, and none of the 5
matches the `verses` table (World English Bible) that `study.py` serves on
click-through:

| Reference | Answer's quoted wording | `verses` table (WEB) |
|---|---|---|
| Ephesians 5:18 | "be continually maintained full of the Holy Spirit" | "be filled with the Spirit" |
| Mark 11:24 | "believe that ye receive them, and ye shall have them" | "believe that you have received them, and you shall have them" |
| Hebrews 4:16 | "receive mercy and find grace to help us in time of need" | "receive mercy and may find grace for help in time of need" |
| 1 Cor 14:39 | "do not forbid speaking in tongues" | "don't forbid speaking with other languages" |
| 1 Cor 14:5 | "I want you all to speak in tongues" | "desire to have you all speak with other languages" |

Three of these (Mark 11:24 = KJV, 1 Cor 14:39 and 14:5 = ESV/NIV) are
legitimate renderings from real translations — the answer simply never names
which. **This is the false-positive class any automated check must not flag**,
and it is why a naive string comparison against `verses` would be useless.

Two are not attributable to a translation:

- **Ephesians 5:18** — "be continually maintained full of the Holy Spirit"
  matches no translation. It is a teaching gloss on the Greek present passive
  imperative (a real and common charismatic reading, and Derek Prince's) placed
  inside quotation marks and credited to the verse.
- **Hebrews 4:16** — "to help **us** in time of need" drifts from both WEB and
  NASB.

Nothing here is doctrinally wrong. The point is the channel: quotation
typography is being applied to Scripture wording that is reconstructed from
training memory, and the verifier passes it because the pointer resolves.

---

## What this means for the biblical-depth work

Increasing scripture density increases traffic through exactly the two
unguarded channels above. The verifier scales with the change on pointers
(more verses cited → more existence checks, all cheap and reliable) and does
not scale at all on wording. Whatever raises depth should be measured against
finding 1's rate, not only against whether references resolve.

---

## Reconciliation

- 5 baseline answers read; 19 quoted spans extracted; 14 compact scripture
  references extracted and resolved against `verses`.
- 7 teacher verbatim quotations probed against live `chunks` by exact
  substring; 4 clean, 1 fabricated, 1 nested-misattributed, 1 altered.
- 3 corpus-wide `ILIKE` counts run to confirm the two absent phrases.
- 0 rows written. 0 model calls. 0 files changed outside this document.

## Adjacent, recorded not investigated

- `scripts/sp1_answer_harness.py` reimplements generation from
  `hybrid_search_rrf` + `ANSWER_SYSTEM_BLOCKS` + a direct Anthropic call. It
  never imports `producer.py`, so it bypasses the position-paper fence,
  stored-position evidence injection, the single-teacher lock, and the
  single-author attribution contract. Any before/after quality comparison run
  through it measures a proxy, not the served path.
- `"Acts 1:5, 8"` — the trailing bare verse is unparseable by
  `_parse_verse_or_range()`, so the second reference in a comma list is never
  verified. Cosmetic here; a general pattern.
- 1 Cor 14:5 is quoted without its second clause, which ranks prophecy above
  tongues. Selective quotation, not misquotation. Noted only.

## Classification

Recommend **Finding 1 for Blocker promotion** under `PLAN.md`'s governing
boundary — it is a demonstrated teacher misrepresentation (ranked failure mode
#2) involving a living minister, in a channel currently believed contained.
Findings 2 and 3 are product-quality and fit Scheduled work.

Promotion is Alex's call, per `AGENTS.md`. Nothing in this audit authorizes a
database write, a prompt edit, or a deploy.

---

## Built in response — `prose_quotation_guard` (same session)

Finding 1 now has a deterministic guard. Findings 2 and 3 do not.

**`backend/app/services/prose_quotation_guard.py`** — pure functions, no I/O,
no model call. A double-quoted span of ≥5 words, attributed to a permitted
teacher name within 400 chars, not Scripture, and not introduced by a negated
construction, must appear verbatim in that answer's retrieved evidence after
punctuation normalization. Anything that does not is returned to the caller.

**`producer.py`** — 17 additive lines. The guard becomes a third arm inside
the existing `_has_ungrounded()`, so it inherits the proven
regenerate-once-then-refuse path rather than introducing a new remedy. Every
flag is logged with the teacher and the quotation, so the false-positive rate
is measurable later — the same discipline Settled #16 requires of the
contradiction filter.

**`scripts/test_prose_quotation_guard.py`** — 23 checks, credential-free,
including 5 mutation proofs that each guard is load-bearing.

### Two things the build changed about the design

1. **Normalization is load-bearing, not cosmetic.** Prince's genuine "what
   brought success in the '60s brings death in the '70s" is stored with curly
   `‘` and written with straight `'`. A raw substring check REJECTS an accurate
   quotation, and the remedy is regeneration then refusal — so without the
   fold this guard would have refused correct answers. Caught by a mutation
   test, not by reading.
2. **Surname attribution was required for recall.** Matching full names only
   missed "Prince warns that…", the shape most attributions take after the
   first mention. The cost is accepted and recorded: a common surname
   ("Brown") can over-trigger near a quotation. One extra generation, against a
   fabricated quote under a living minister's name, is not a close trade.

### Measured behaviour on the five real baseline answers

3 flags, all 3 true positives (fabrication, alteration, truncation), zero false
positives. Two false positives existed before the negated-introduction
exclusion was added — hypothetical non-quotations the answer was explicitly
denying ("There is no passage that says, '…'").

### What it does NOT do — stated so it is not over-claimed

- **Nested quotation is not caught.** Grudem's words credited to Kolenda pass,
  because they genuinely are in the retrieved chunk. Asserted as a test that
  fails if this ever changes, so a future session cannot mistake it for
  coverage.
- **Scripture is out of scope entirely** (findings 2 and 3). Quoted verses are
  deliberately excluded; teacher chunks are the wrong haystack for them.
- **Not deployed, not verified in production.** Repo-only. No live answer has
  run through it.
