# Author attribution audit — 2026-08-31

Read-only. SELECT-only against the live database through a read-only
transaction; zero writes, zero DDL. Method: `documents.author` joined to
`sources`, grouped by `citation_mode`.

> **RESOLVED the same day — both halves.** Root cause fixed forward in
> `scripts/youtube_ingest.py` (`_verified_speaker()`, commit `fe0718a`, with
> `scripts/test_youtube_speaker_attribution.py`, 22 checks including a mutation
> proof). The seven existing rows were repaired by an attended write:
> `scripts/archive/2026-08/fix_unverified_authors_2026-08-31.py --apply`,
> `UPDATE 7`, committed, reconciled from a fresh connection. Citable author
> groups went **55 → 48**; zero citable rows carry any target string. Findings
> 1 and 2 below are the historical record of what was wrong, not open work.

**Why only citable rows matter.** `reference_verifier.build_retrieval_grounding()`
builds `author_keys` from the author of *citable* evidence. A `silent_context`
document cannot put a name into an answer's permitted-name set, so a malformed
author there is cosmetic. A malformed author on a **citable** row is not.

## Scope

| Measure | Count |
|---|---|
| Documents carrying an author | 3,529 |
| Distinct author strings | 393 |
| Citable author/source groups | 55 |
| Documents behind those citable groups | 2,582 |

## Finding 1 — five title fragments are citable authors `LIVE DEFECT`

All five sit under the **Vlad Savchuk** source, one document each:

| `documents.author` | Mode |
|---|---|
| `Day Abortion` | citable |
| `Do This Instead` | citable |
| `Watch Message` | citable |
| `Your Porn Battle Plan` | citable |
| `This Is How You Should Fight Your Battles` | citable |

These are title fragments captured by the speaker parser, not people. Each one
enters the permitted-name set for its document's evidence, so the answer writer
is told these are legitimate names it may attribute claims to.

This is the same defect class CLAUDE.md already records for the parser artifact
`Sunday` (from "… | Sunday Message"). The standing instruction — *check
`documents.author` after any title-derived ingest; the speaker parser is not
reliable* — was correct and under-applied.

## Finding 2 — two identity splits on the same source `LIVE DEFECT`

`Vlad` (1 doc) and `Pastor Vlad` (1 doc) are citable alongside the canonical
identity. Each draws its own share of the per-author 3-chunk cap, exactly like
the `Pastor Paul Kidd` / `Paul Kidd` split already recorded for CLF.

## Finding 3 — comma-joined authors are fully resolved `NO ACTION`

All four comma-joined groups are `silent_context`. Nothing to fix.

| Author | Docs | Mode |
|---|---|---|
| `Jamieson, Fausset & Brown` | 65 | silent_context |
| `Paul Kidd, Shabaka Williams` | 2 | silent_context |
| `Paul Kidd, Alex Whitley` | 1 | silent_context |
| `Paul K., Nneka H., Tiffany C., Shabaka W.` | 1 | silent_context |

The three CLF rows were silenced 2026-08-31 as recorded. `Jamieson, Fausset &
Brown` is a genuine joint-authored public-domain commentary, correctly silenced
and **not** a defect — do not "fix" it.

**Method note worth keeping:** read from the public `/corpus-inventory/export`
endpoint alone, these four look like four live problems, because that endpoint
exposes `author` but not `citation_mode`. The distinction only exists in the
database.

## Finding 4 — the bulk of Savchuk's citable corpus has a NULL author

119 citable Savchuk documents carry `author = NULL`, and the served citation
falls back to the source name. This is working correctly — a live smoke answer
displayed "Vlad Savchuk" and grounded the teacher reference to a real
`source_id`. Recorded so nobody "repairs" the NULLs into per-document strings
and reintroduces Findings 1 and 2 at scale.

## Finding 5 — guest speakers, decided not open

Single-document citable authors, mostly New Wine Magazine contributors and CLF
guests: `Alan Banks`, `Dennis Moses`, `Don Flora`, `Eric Davis`, `Jim Croft`,
`John Poole`, `Kay Oswald`, `Len J. Jones`, `Morris Hatfield`, `Moses Ng'etich`,
`Paul Petrie`, `Peter Kamau`, `Tiffany Davis`, `Wayne Conrad`, and others.
`Alex Whitley` is citable on 2 CLF documents.

**Alex ruled 2026-08-31: leave as-is.** Recorded as a closed decision, not an
open finding, so it stops resurfacing in status sweeps.

## Adjacent finding — a served citation carried a dangling `chunk_id`

Not part of this audit's scope; recorded for classification, not investigated.

The 2026-08-31 post-deploy smoke answer returned a citation whose `chunk_id`
`0b9d1930-7103-4520-8e37-e382dc7b3227` matches **zero** of the 186,944 rows in
`chunks`. The cited *document* resolves normally
(`cf027bfa-9006-4c6d-acc7-575d9429b6ad`, citable, Vlad Savchuk), and the answer
itself was correct and correctly attributed.

Two readings, undecided: either citation `chunk_id` values do not correspond to
`chunks.id` at all (in which case this is a naming/contract question, not a
bug), or a served citation can point at evidence that cannot be resolved back.
The second would matter for the beta journey item "inspect citations/evidence."
Needs one deliberate check of how `producer.py` populates the field before
anyone concludes either way.

## What this audit does NOT establish

- Whether the five artifact authors ever actually caused a wrong attribution in
  a served answer. No answer-log review was done.
- Whether other sources beyond Savchuk carry title-derived authors that happen
  not to look like prose. The detection here was heuristic plus manual review of
  55 citable groups, not exhaustive parsing.
- Anything about non-citable rows, deliberately out of scope.
