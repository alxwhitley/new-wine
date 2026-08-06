# Sourcing Notes — Deliverance and Spiritual Warfare

For Alex's eyes only. Not part of the draft, not to be merged into it. This
records where the draft's claims actually came from in the corpus, so you can
see which sections are real corpus consensus and which are closer to one
teacher's view with the name filed off.

Method: read-only SELECT queries against `propositions` joined to `documents`
via `SUPABASE_DB_URL`, matching content on word-boundary patterns for
deliverance/demon/demonic/exorcism/stronghold/spiritual warfare/oppression/
possession/casting out. No writes of any kind were performed.

## Overall corpus coverage on this topic

358 propositions across roughly 3,595 documents matched the search terms
after cleaning up false positives (the naive first pass over-matched on
"demonstrate"/"demonstration" against the "demon" stem — the number below is
the corrected count). That's a real but not huge slice of the corpus.

Teacher breakdown (propositions / documents), after manually reconciling
`author` vs `source_name` mismatches described below:

| Teacher | Propositions | Documents |
|---|---|---|
| Derek Prince | 228 | 111 |
| Vlad Savchuk | 94 | 37 |
| Doug Kreighbaum | 14 | 1 |
| Zac Poonen | 4 | 4 |
| Daniel Kolenda | 3 | 3 |
| Carter Conlon | 2 | 2 |
| Leonard Ravenhill | 2 | 2 |
| Smith Wigglesworth | 2 | 1 |
| New Wine Magazine (Bob Mumford, Charles Simpson, Don Flora, Kay Oswald, Wayne Conrad) | 1 each | 1 each |

**Read this as two real teachers plus a long thin tail.** Derek Prince and
Vlad Savchuk together are ~90% of everything the corpus has on this topic.
Everyone else is a handful of incidental mentions inside documents that are
mostly about something else — not a second or third independent teaching
voice on deliverance specifically. Treat any claim in the draft NOT
attributable to Prince or Savchuk as thin, single-mention support.

**Data quality note, not a corpus-content finding:** several Vlad Savchuk
documents have garbage values in `documents.author` (e.g. "Pastor Vlad",
"Watch Message", "Day Abortion", "This Is How You Should Fight Your
Battles") instead of his name — `source_name` was reliable where `author`
wasn't, so I used both. Separately, one "Zac Poonen" row uses a non-breaking
space (U+00A0) instead of a regular space in `author`, which would silently
split him into two authors under any query that doesn't normalize whitespace
(relevant to CLAUDE.md's `normalize_alias_key` invariant — this isn't that
function, but it's the same failure shape). Flagging in case this surfaces
elsewhere; not something I fixed.

## Section-by-section sourcing in the draft

- **What It Is / Jesus Made This Ordinary** — Scripture-led (Mark 1, Luke 4,
  Luke 10, Matthew 10, Mark 16, Acts 10:38). Corpus support: broadly Derek
  Prince structurally, consistent with Savchuk's framing. Real consensus, not
  one teacher's idiosyncratic reading.
- **The Believer's Authority Is Real** — same: scripture-anchored, and both
  major teachers use this material (Ephesians 6 armor-of-God content is
  actually more heavily represented in Prince's corpus material than
  Savchuk's, by volume — see the armor/authority query, dominated by Prince).
  Solid.
- **How Demons Operate** — this section is Derek Prince's material almost
  exclusively (his "six forms of demonic activity: enticing, enslaving,
  tormenting, driving/compelling, defiling, harassing" framework, and the
  Matthew 12:43-45 restless-spirit material). Savchuk's content is compatible
  with it but doesn't independently build the same taxonomy. **This section
  is closer to one teacher's systematic framework than corpus consensus** —
  it just happens to be the corpus's dominant voice on the topic, so I judged
  it fair to lead with, but it's worth knowing it's Prince's structure, not
  an average of several teachers.
- **The open question (flagged in the draft)** — see below, own section.
- **Discernment Comes Before Deliverance** — this is almost entirely Doug
  Kreighbaum ("Dealing with the Demonic," 14 propositions, his only document
  in this cluster) plus Vlad Savchuk's caution material (his "not every issue
  is a demon," "don't rush to cast out demons," brain-tumor-mistaken-for-
  possession example, and his five-pitfalls-of-deliverance-ministry content).
  Two independent teachers landing on the same caution is real agreement,
  not padding — but it's two teachers, not a corpus-wide consensus, and
  Kreighbaum's entire contribution to this whole paper is one document.
- **Common Objections** — drew on Prince (the "already won victory, fought
  from not for" framing, which is explicitly Savchuk's own phrase actually —
  "we fight demonic spirits not for victory, but from victory" is a direct
  Savchuk proposition, not Prince's) and Kreighbaum/Savchuk's caution
  material for the other three answers. The Acts 19 sons-of-Sceva point in
  the "risky to try yourself" answer is my own scriptural addition — I did
  not find it discussed in the matched corpus material at all. Flagging that
  explicitly since the instruction was to say so when I pad past what's
  actually there: **that one answer's supporting scripture is not
  corpus-sourced**, only the underlying "act under real authority, not
  imitation" point is.
- **What This Is Not Saying** — synthesized from the discernment material
  above (Kreighbaum, Savchuk) plus my own inference from the pattern of what
  both teachers explicitly warn against. Reasonable synthesis, not a
  fabrication, but worth knowing it's inference from caution statements
  rather than any teacher stating "here is what this is not saying" as such.

## The disagreement flagged in Step 4

This is the important one, and it's more subtle than a straightforward
two-sided fight, so I want to be precise about exactly what's in the corpus
rather than round it off.

**What's actually there:** Vlad Savchuk explicitly and repeatedly stakes out
a position — "Christians can have demons," stated in those words, arguing
against what he calls "traditional teachings" that say otherwise, and against
the idea that this "hinders deliverance." That's a real, direct, corpus-
sourced claim from a real teacher (see "7 Signs You're Called to Cast Demons
Out" and related documents).

**What's NOT there:** no teacher in this corpus argues the opposing side —
that a genuine, Spirit-indwelt believer cannot have an indwelling demon and
can only be oppressed from outside — in their own words. I searched
specifically for that position (cannot-be-possessed / oppression-only
framing) and found nothing from any named teacher taking it. Savchuk's
"traditional teachings" opponent is described, not present as a voice.

**Where Derek Prince actually lands:** closer to Savchuk than I initially
expected, but hedged in a way that matters. Prince explicitly teaches that
"demons can move in and occupy certain areas of a person's life, even if
they are a Christian" — so he agrees a believer's life can have demonic
occupation in some real sense. But he consistently prefers "demonized" over
"possessed," specifically to avoid the stronger claim of total ownership,
and he never states it as flatly as Savchuk does ("Christians can have
demons"). So the two aren't in open contradiction, but they're not saying
the identical thing either — it reads more like a difference of emphasis and
carefulness than a clean two-sided debate.

**My recommendation:** the draft's placeholder is honest about this — it
says the corpus leans one direction without ever stating the strongest form
of that view, and that no source argues the opposite side directly. I did
not soften this into "some say X, others say Y" because that would overstate
how contested the corpus itself is — the real finding is closer to "the
corpus's dominant voice hedges carefully; a second voice states it more
bluntly; a real third position exists in the wider tradition but isn't
independently represented here at all." You may want to leave the paper's
language cautious for exactly that reason, or you may know from outside the
corpus that this deserves a firmer stated position — that's the call the
placeholder is asking you to make, not something I should resolve by
guessing at your intent.

## Thin-coverage spots, stated honestly

- **Anything specific to exorcism terminology, or possession in the classic/
  clinical sense** — essentially unaddressed directly; the corpus uses
  "demonized"/"oppressed" almost exclusively, so I did not force
  "exorcism"-specific content into the draft.
- **Deliverance and mental illness / the differential-diagnosis question** —
  covered, but by exactly one document (Kreighbaum) plus a handful of
  Savchuk propositions (the brain-tumor example, the anxiety-has-spiritual-
  roots material). Real, but thin. If this paper gets scrutinized hardest
  anywhere, it'll be here.
- **Deliverance ministry practice/methodology beyond Prince's six steps** —
  Prince is thorough on the individual's own steps (humility, honesty,
  confession, repentance, forgiveness, calling on the Lord) but the corpus
  says very little about how a minister/team should run an actual deliverance
  session with someone else, beyond Kreighbaum's general cautions. I kept the
  draft's practice description brief for this reason rather than padding it.

## Binding and loosing — recommendation: own paper, not a section here

Searched separately per Step 3. Result: 7 propositions, 4 documents, one
teacher (Derek Prince) — by a wide margin the thinnest cluster I looked at
in this whole pass. Nobody else in the corpus touches it in any form I could
find, even under a broadened word-form search (bind/binding/loose/loosed/
bound, which pulled in a lot of noise from unrelated uses of those words and
still surfaced no additional teacher on the actual Matthew 16:19/18:18
authority concept).

Recommendation: **its own (short) paper later, not a section grafted onto
this one.** Two reasons. First, coverage is too thin to write anything past
"Derek Prince's view restated" — there's no synthesis to do with one source,
and this paper's whole premise is that it has no citation to lean on, so a
single-teacher section would be the exact risk Step 5 warned about, just
inside a bigger document instead of standing alone. Second, it's
conceptually a different topic — corporate/authoritative prayer declaration
("binding" a work of the enemy, "loosing" a blessing) rather than the
personal-affliction-and-freedom ministry this paper is about. Bolting it on
would blur both topics rather than clarify either.
