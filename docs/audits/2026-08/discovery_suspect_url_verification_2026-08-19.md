# Discovery-tab suspect URL verification — 2026-08-19

Read-only verification of the two rows CLAUDE.md's Landmines section flagged
as known-suspect and unverified in `docs/ingestion/master_ingestion_queue.xlsx`
(Discovery tab): Loren Cunningham and Reinhard Bonnke, both deceased, both
listed with clean, live-looking personal domains under `claimed_main_url`.
No spreadsheet or database write occurred; this file is the only output.

## Loren Cunningham — VERDICT: legitimate

- `claimed_main_url`: `https://lorencunningham.com/`
- Fetched directly: a professionally hosted (Squarespace) memorial/legacy
  site — Articles, Memorial, About, Books sections, official YWAM logo and
  footer link to `ywam.org`, multiple biographical articles, his published
  books, memorial videos, and direct family contributions (his wife Darlene,
  daughter Karen), including "The 6 million mile man" anecdote and 1960
  YWAM-founding detail.
- Cross-check: independently surfaced by web search as `LorenCunningham.com`,
  including a direct in-site link from `ywamkona.org/loren-cunningham-is-with-jesus/`
  ("A Message from Darlene — LorenCunningham.com") and referenced alongside
  `ywam.org/loreniswithjesus` and `kb.ywam.org/kb/Loren_Cunningham`. The
  official YWAM ecosystem treats this domain as the legacy site, not an
  unrelated or reassigned one.
- No red flags: substantive original content, family voice, working
  cross-links to/from the official org. Safe to keep as the claimed URL.

## Reinhard Bonnke — VERDICT: suspect, do not trust as-is

- `claimed_main_url`: `https://reinhardbonnke.com/`
- **HTTPS fetch failed: "certificate has expired."** Both `https://` and
  `http://` attempts failed the same way — the site could not be loaded
  securely at all during this check. A browser would show a hard security
  warning, not a clean page.
- The official Christ for all Nations page (`cfan.org/reinhard-bonnke`) makes
  **zero reference** to `reinhardbonnke.com` anywhere. It points instead to
  CfaN's own gospel booklets, the "Full Flame Film Series," and CfaN's own
  channels as the authoritative repository of his work — no external
  biographical/legacy domain is cited.
- A web search snippet claimed "Reinhard Bonnke's official blog is
  www.reinhardbonnke.com," but that could not be independently confirmed —
  it directly conflicts with the expired-cert/unreachable state observed
  live and the absence of any link from CfaN's own official page. Treat that
  snippet as stale/cached metadata, not a live fact.
- This matches exactly the red-flag pattern CLAUDE.md flagged: a deceased
  minister's domain that looks clean on paper (a plausible name-match URL)
  but shows real signs of neglect (expired cert = lapsed maintenance, and an
  expired cert also raises the risk the domain itself could lapse and be
  re-registered by an unrelated party). **Do not ingest from this URL as
  claimed.** If Bonnke content is wanted for the corpus, source it from
  CfaN's own official channels (`cfan.org`, `cfan.uk`, `cfan.eu`) instead,
  and re-verify `reinhardbonnke.com` manually (accepting/inspecting the
  expired cert in a real browser, checking WHOIS/registration history) before
  ever treating it as authoritative.

## Out of scope, noted in passing

A third row in the same Discovery tab, **Darlene Cunningham**
(`claimed_main_url: https://darlenecunningham.com/`, `living_or_deceased:
unknown`), follows the identical claimed-personal-domain pattern as the two
flagged rows but was not in scope for this check and was not fetched. Worth
the same treatment before trusting it.
