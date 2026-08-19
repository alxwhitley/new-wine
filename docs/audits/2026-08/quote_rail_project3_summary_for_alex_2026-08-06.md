# Quote Review Prep — Andrew Murray & Derek Prince (plain-English summary)

This was a look-only pass — nothing was changed, built, or extracted. The
goal was to find out what material is actually available for each teacher
and what (if anything) is already built toward the quote-review tool.

## Andrew Murray

10 books are available. One of them — "The New Life" — starts with a few
pages that aren't Murray's own writing: a short description written by the
library that digitized the book, and a note from the person who translated
it into English, signed and dated 1891. Murray's own writing (his Preface,
then the book itself) starts right after that. This section needs to be
skipped before anyone reviews quotes from that book, and it's now pinned
down precisely enough that it can be excluded cleanly. The other 9 books
didn't get this same check yet — worth a quick look before relying on them,
since 3 of the 10 came from the same library and could have the same kind of
front-matter issue, though nothing suggests they do.

## Derek Prince

496 pieces of teaching material are attributed to him. Of those, 491 are
recorded and tagged in the system as sermon recordings that were
transcribed into text — not material he sat down and wrote. Only 5 are
tagged as magazine-style articles, which look more like genuinely written
material. This is worth flagging clearly: it runs against what I understood
coming in, that everything under his name was originally written work. I
did not go back and check whether the transcriptions themselves are
accurate — that wasn't the task — I'm only reporting what the system's own
records say about where this material came from. It matters because the
product's existing rule for quotes treats transcribed material differently
from material an author actually wrote, requiring extra checking before
it's usable.

Two other documents turned up in the search because they share the name
"Prince" — they belong to Ruth Prince, Derek Prince's late wife, who is
tracked separately in the system. Those two are correctly excluded from his
count above.

Also worth knowing: about 1 in 6 of his pieces are part of multi-part
teaching series (a few 2-part ones, one 20-part series, one 21-part series,
and two 5-part groupings) rather than standalone pieces. That's tracked in
the system already, but nothing about quote selection currently uses that
grouping — worth keeping in mind so a single teaching doesn't end up
over-represented just because it was split into many pieces.

## Neither teacher has any commentary material mixed in

Checked directly — clean on both sides.

## What already exists for the quote tool, and what doesn't

There's an old, unused table left over from an earlier attempt, and an old
script that used AI to freely generate quote text without checking it
against the actual source. Both were already set aside before this session,
and neither is usable for the approach that was decided on since (every
quote must be manually reviewed and approved by a person, never generated or
approved by AI). Nothing has been built yet for that current approach — the
actual review tool, the quote table, and the safety checks all still need
to be built from the ground up. This audit didn't start any of that.

## Decisions needed from Alex

1. **Derek Prince's material is mostly transcribed sermons, not written
   work.** How should this affect what's eligible for quote review, given
   the product's existing rule that transcribed material needs extra
   verification before it can be quoted? This needs your call before quote
   review can meaningfully start on his material.
2. **Should the other 2 Andrew Murray books from the same library source
   get the same front-matter check** before quote review starts on them, or
   is it fine to check each book as it comes up for review?
