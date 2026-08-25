# Discovery Candidate Review Tool Design

**Date:** 2026-08-25

**Status:** Confirmed by Alex; ready for implementation planning

**Scope:** A local, single-user review tool for moving Discovery-tab
candidates into the Approved Sites tab of
`docs/ingestion/master_ingestion_queue.xlsx`. No database, no deployment, no
change to `sync_master_ingestion_queue.py` or `site_ingest_crawler.py`.

## Objective

Today, promoting a Discovery-tab candidate to Approved Sites means manually
opening each claimed URL, judging the content by hand, then hand-typing a new
row into the Approved Sites tab. There is no record of "I looked at this and
passed" and no fast way to record a verdict. Of 118 Discovery rows, 118 are
still `unverified`.

This tool doesn't replace the manual judgment call (Alex still visits each
site and decides) — it removes the friction around recording that judgment:
one candidate at a time, real spreadsheet links to click, and a one-click
Approve/Reject/Skip that writes the correct rows immediately, so working
through the backlog is fast and nothing has to be retyped by hand.

## Context: what already exists

- **Discovery** tab (118 rows) — raw, unvetted candidates from automated
  research passes. Every `claimed_*` column is asserted, not established.
  `verification_status` defaults to `unverified` and already has a
  data-validation list of `unverified, in_progress, verified, rejected` —
  `rejected` exists in the schema today but nothing sets it yet.
- **Approved Sites** tab (19 rows, 1 approved) — `approved`, `name`,
  `attribute_to`, `blog_url`, `authorship_confidence`, `scale_note`,
  `proposal_notes`, `approved_at`. This is the tab Alex hand-edits today.
  `site_ingest_crawler.py` reads only rows here where `approved` is
  literally `TRUE` — this tool's only interaction with the crawler is
  producing rows it can read; the tool never invokes the crawler itself.
- **Queue** tab — unrelated to this tool; fully-specified single-document
  rows synced to the database by `sync_master_ingestion_queue.py`.

## Approved Product Decisions

1. **Review mode:** Alex clicks around the actual candidate site himself
   (claimed URLs open in a new browser tab); the tool does not auto-fetch or
   embed content previews.
2. **Interface:** a local browser page, not a terminal UI.
3. **Site browsing:** every claimed URL is a plain `target="_blank"` link.
   No iframe embedding attempt (most sites block it via
   X-Frame-Options/CSP anyway) — always open in a new tab.
4. **Approve:** opens a small inline form, pre-filled with best guesses,
   before it writes the Approved Sites row.
5. **Reject:** permanently excludes the candidate — `verification_status`
   is set to the existing `rejected` value and the tool never surfaces that
   row again.
6. **Out of scope for this build** (explicitly not building): auto-fetched
   content previews, embedded live browsing, and auto-triggering
   `site_ingest_crawler.py` after an approval. All three are reasonable
   future add-ons, not part of this tool.

## Architecture

```text
scripts/review_discovery_candidates.py
        │  (single file, FastAPI app; fastapi/starlette/uvicorn are
        │   already pinned in backend/requirements.txt — no new dependency)
        │
        ├─ load_queue()         builds the in-memory review queue from
        │                       Discovery rows on startup
        ├─ GET  /                render the current candidate card
        ├─ POST /approve         validate → reload workbook → write
        │                        Approved Sites row + Discovery row →
        │                        save → advance → redirect to /
        ├─ POST /reject          validate → reload workbook → write
        │                        Discovery row → save → advance →
        │                        redirect to /
        ├─ POST /skip            advance in-memory pointer only, no write
        └─ openpyxl              direct read/write of
                                 docs/ingestion/master_ingestion_queue.xlsx
```

Run with `python3.12 scripts/review_discovery_candidates.py` (optional
`--port`, default `8765`). The tool opens the browser itself
(`webbrowser.open`) on startup. Binds to `127.0.0.1` only — this is a
personal local tool, same trust posture as the other scripts in
`scripts/`; no auth, no network exposure.

HTML is built from plain Python string templates, not a templating engine —
avoids adding a `jinja2` dependency for a page this small.

## Queue definition and ordering

The review queue is computed once at process startup from the Discovery
tab, in sheet row order:

```text
verification_status == "unverified"
  AND already_in_corpus != True
  AND claimed_written_content_exists != False
```

(~104 of 118 rows today.) Already-in-corpus and confirmed-no-content rows
are excluded — reviewing either wastes a click for no decision to make.

No separate progress-tracking file. Because Approve/Reject change
`verification_status` away from `unverified`, a restarted process naturally
resumes at the next still-`unverified` row in sheet order — the filter
itself is the resume state.

**Skip** only reorders the *in-memory* session queue — the skipped
candidate moves to the back of this run's list so a sitting doesn't loop on
it repeatedly, but nothing is written to the sheet. If the tool is
restarted, a skipped candidate reappears (still `unverified`) — acceptable,
since skip is "not now," not a verdict.

## Components and Interfaces

### `GET /`

Renders the current candidate: name, organization, location, category,
living_or_deceased, every claimed URL as an `<a target="_blank">` link
(`claimed_main_url`, `claimed_blog_or_articles_url`, `archive_url`,
`other_urls`), `claimed_licensing_status`, `claimed_platform_size`,
`corpus_match_notes`, `claims_source`, `notes` — everything useful for
judgment, read-only. Shows "N of M reviewed this session" and three
actions: Approve, Reject, Skip. If the queue is empty, renders an
"All caught up" screen with the session's approve/reject counts.

### `POST /approve`

Form fields, pre-filled from the Discovery row and editable before submit:

- `attribute_to` (required, default = `name`)
- `blog_url` (required, default = `claimed_blog_or_articles_url` or, if
  blank, `claimed_main_url`)
- `authorship_confidence` (required, free text — matches every existing
  Approved Sites row)
- `scale_note` (optional, free text)
- `proposal_notes` (optional, free text)

On submit:

1. Refuse if the Excel lock file is present (see Error Handling).
2. Reload the workbook fresh.
3. Refuse (inline error, no write) if `name` (case-insensitive, trimmed)
   already exists in Approved Sites — no silent duplicates.
4. Append a new Approved Sites row: `approved="TRUE"`, the four submitted
   fields, `approved_at` = `f"{today} -- review tool approval (Discovery: {name})"`
   — matching the existing manual style
   (`"2026-08-25 -- chat approval (...)"`).
5. On the Discovery row: `verification_status="verified"`,
   `reviewed_at=<now, ISO date>`, `review_notes="Approved -> Approved Sites"`.
6. Save. Advance the queue. Redirect to `/`.

If the save raises, nothing advances; the same candidate re-renders with the
error shown and the form fields preserved.

### `POST /reject`

One required field: `reason` (free text).

On submit: same lock-check → reload → save discipline as Approve. Sets
`verification_status="rejected"`, `reviewed_at=<now>`,
`review_notes=<reason>` on the Discovery row. No Approved Sites write.
Advance. Redirect to `/`.

### `POST /skip`

No file I/O. Moves the current candidate to the back of the in-memory
queue. Redirect to `/`.

## Schema change: two new Discovery columns

`reviewed_at` and `review_notes`, appended after the existing
`agent_verification_notes` column. Kept separate from `notes` and
`agent_verification_notes` deliberately — those are automated-research
provenance ("claimed", "asserted"); these two are Alex's own manual
verdict, and this sheet's existing convention (per its Read Me tab) is to
keep those two kinds of information visibly distinct rather than blending
them into one free-text column.

The Read Me tab gets a short dated addendum documenting the new columns and
this tool's existence, matching the sheet's existing pattern of dated
schema-change notes (e.g. the 2026-08-19 addendum already in that tab).

No changes to the Approved Sites or Queue tab schemas, and no data
validation list is added to Approved Sites' `approved` column (it has none
today; out of scope to add one here).

## Error handling and safety

- **Excel lock check:** if `docs/ingestion/~$master_ingestion_queue.xlsx`
  exists, the tool refuses to start, and refuses every write attempted
  while it exists — clear message: close the workbook in Excel first. (It
  exists right now, as of this session.)
- **Write discipline:** one row-write per action, saved immediately — no
  batching, no held-open write transaction. If a save fails for any reason,
  the queue pointer does not advance and the error is shown inline; the
  operator sees exactly what happened and nothing is lost.
- **No duplicate Approved Sites rows** — refused inline, by name match.
- **Recovery:** this file is deliberately git-tracked specifically so git
  history is its backup/recovery mechanism (Alex's existing standing
  decision) — this tool adds no separate backup step.
- Local-only (127.0.0.1), no auth — consistent with every other script in
  `scripts/` that assumes a trusted local operator.

## Testing strategy

- Unit tests for the pure logic — queue filtering/ordering, and the
  Approve/Reject row-mutation functions — run against a small throwaway
  test workbook built in a temp directory, never the real file.
- One manual smoke test before calling the build done: run the tool
  against a scratch copy of the real `master_ingestion_queue.xlsx`,
  approve one candidate and reject another through the actual browser UI,
  then reload the scratch copy with `openpyxl` and confirm: the right
  cells changed in both tabs, and the existing data-validation dropdowns
  on Discovery (`verification_status`, etc.) are still present after the
  openpyxl round-trip save. This is a one-time proof, not an automated
  regression test — matches how `site_ingest_crawler.py`'s real proof was
  a one-time live run.
- No live-DB tests — this tool never touches the database.

## Boundaries (explicitly not building)

- No content pre-fetching or preview rendering.
- No iframe embedding of candidate sites.
- No automatic `site_ingest_crawler.py` invocation after approval.
- No change to how `site_ingest_crawler.py` or `sync_master_ingestion_queue.py`
  read the workbook — both are untouched by this build.
- No un-approve / un-reject flow from within the tool (the spreadsheet
  remains hand-editable for corrections, as today).
- No keyboard shortcuts (click-only for this build; cheap to add later if
  Alex wants it after using the tool for a while).

## Success criteria

- Alex can run one command, get a browser page, and work through the
  Discovery backlog one candidate at a time without ever hand-typing a row
  into Approved Sites or hand-editing `verification_status`.
- An Approve always produces a correctly-shaped Approved Sites row
  (matching the columns `site_ingest_crawler.py` requires:
  `approved`, `blog_url`, `attribute_to`) on the first try.
- A Reject is permanent and the row never resurfaces in a later run of the
  tool.
- Restarting the tool mid-backlog loses no completed work and does not
  reprocess already-decided rows.

## Open questions for the implementation plan

- Exact wording for the two or three quick-pick reject reasons (if any are
  worth offering as buttons alongside free text) vs. free text only — free
  text only is the default per this spec; add presets only if Alex asks
  after using it.
