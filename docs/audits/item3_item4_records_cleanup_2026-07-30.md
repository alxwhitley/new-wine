# Item 3 / Item 4 documentation cleanup — 2026-07-30

**Plain-English summary:** Two project files (PLAN.md and rhemata-status.md) still described three known code fixes as outstanding, even though those fixes were completed and verified earlier today. Both files have been updated in place to say plainly that the work is done, without erasing the history of what was originally requested. One honest caveat carried forward from the actual fix: the wording change alone did not solve the underlying over-confidence risk on the Calvinism/predestination topic — that remains a separately tracked open item, and neither file now implies otherwise. A small piece of the original request (a decision on some edge-case topic names) was never part of today's fix and is now called out explicitly as still unmade, rather than left ambiguous.

This was a documentation-only session — no code or database changes.

---

## What was found and fixed

**PLAN.md** — the "Item 3" and "Item 4" entries (in the Position layer build section) both still read as if the three repairs were unconfirmed or only partially done. Added a dated update to each stating plainly that all three repairs are complete, with a pointer to the verification evidence, while leaving the original historical text in place rather than rewriting it (matching this file's own established convention of appending corrections instead of erasing prior entries). Also added a new version-history entry (bumped v5.9 → v5.10) summarizing the change.

**rhemata-status.md** — a separate, still-pending section from another session ("Position layer Item 3 shipped; review repairs gate Item 4") had a heading and a "next step" line that both framed the repairs as an unmet blocker. This session's instructions explicitly authorized correcting that specific claim in place (a narrower, more direct edit than a prior session's instruction to leave that section untouched) — so the heading and the "next step" line were both updated to state the repairs are complete, while the rest of that section (describing what the original review actually found) was left as-is.

## Final sweep

Searched both files for any other reference to the three repairs as outstanding, pending, or owed. Found two more places carrying the same stale framing — an existing "correction" note in rhemata-status.md that still said the regression-test suite was "not confirmed to exist," and a version-history entry describing the same. Both were part of the two edits above and are now consistent with the rest.

## What was deliberately NOT changed

- The two frontend commentary files (`commentary-accordion-row.tsx`, `format-commentary-content.tsx`) — untouched, unrelated to this work, left exactly as found.
- The body of rhemata-status.md's pending section describing what the original post-commit review found — that description is still accurate as a historical record of the review's own findings; only the "still blocking" framing around it was corrected.
- Any historical version-history bullet describing what was true at the time it was written (e.g. "stamp `position_tension_v1`," "inserted via f-string substitution") — these remain as accurate descriptions of that point in time, immediately followed by a note explaining what's different now, rather than being rewritten.
- One item from the original post-commit review — an explicit accepted/rejected ruling on matcher variants like "predestined" or "Calvin on election" — was never part of today's three repairs and is now called out plainly in both files as still unmade, not silently implied as done.

## Files touched

- `/Users/alexwhitley/rhemata/PLAN.md`
- `/Users/alexwhitley/rhemata/rhemata-status.md`

## Commit

- `cec6fa9` — both files, one records commit.
