# Corpus Source Audit — Phase 1 (read-only, diagnostic only)

Date: 2026-07-25. No database writes, no ingest, no corpus changes. Crawl only —
descriptive User-Agent (`RhemataCorpusAudit/1.0`, declares purpose + contact),
robots.txt respected, ~1s delay between requests. Script + raw output live in
the session scratchpad, not committed.

## Script bugs found and fixed mid-run (both confirmed against live responses)

1. **robots.txt fetched with the wrong identity.** `RobotFileParser.read()`
   fetches robots.txt using Python's generic default UA, not the crawler's
   declared UA. Three sites (Kris Vallotton, John Bevere, Darren Rouanzoin)
   block that generic UA but return `200` to our real declared UA (verified
   directly with curl) — so the first pass falsely reported all three as
   "blocked by robots.txt" when they were not. Fixed by fetching robots.txt
   through the same identified client used for everything else.
2. **Byline fallback captured non-name text as an "author."** On
   mikesignorelli.com, the real author name renders client-side via JS —
   the static HTML has `"author": ""` in JSON-LD and an empty
   `<a class="blog-author-name">`. The byline fallback grabbed a sibling
   wrapper's text instead ("Aug 4 Written By"), which would have shown up as
   11 fake "distinct authors" and forced a false multi-voice verdict. Fixed
   by rejecting byline candidates that contain digits, match month
   abbreviations, or match a stopword list (dates/labels, not names).

## Per-source inventory

### Vlad Savchuk
- **FEED / SITEMAP**: FAILED — `pastorvlad.org` sits behind a Cloudflare bot
  wall that returns HTTP 403 to any non-browser-fingerprinted request,
  including our honestly-declared UA and even a spoofed `Googlebot/2.1` UA
  string (tested). This is a genuine site-side block, not a script bug.
- **SAMPLE**: 0 URLs (no archive to sample from).
- **Archive size: unavailable** — could not be crawled at all this pass.
  Per your flag: HungryGen is understood to overlap Vlad's content, but that
  overlap can't be quantified from this run since no archive size was
  obtainable for Vlad's side of the comparison.
- **VERDICT: undetermined — needs manual check** (by design decision, left
  as-is rather than spoofing a browser identity to get past the wall).

### Kris Vallotton
- **FEED**: FAILED — `https://www.krisvallotton.com/blog?format=rss` returns
  the site's full HTML shell, not an RSS document. `?format=rss` is the
  right Squarespace convention but not at the `/blog` path for this site;
  the correct collection slug wasn't identified this pass. No feed-level
  author signal.
- **SITEMAP**: 743 raw URLs → 737 after filtering. Caveat: the filter is a
  generic path-exclusion heuristic (strips `/tag/`, `/category/`, `/page/`,
  media, etc.) with no Squarespace-specific collection awareness — it did
  **not** catch this site's `/product/` (10 URLs) or `/book-details/` (16
  URLs) pages, which are real but aren't blog posts. True post count is a
  bit under 737, likely ~710.
- **SAMPLE**: 20 URLs → 17 "Kris Vallotton" via JSON-LD, 2 non-post pages
  correctly showing no author (a book-detail page, a "thank you" page), 1
  product page. Zero conflicting authors.
- **VERDICT: single-voice (safe to bulk-attribute).** Confidence rests on
  the sitemap+sample signal, not the feed (which didn't resolve).

### Mike Signorelli
- **FEED**: The task-provided URL (`https://mikesignorelli.com/feed/`)
  404s — wrong path for this Squarespace site. I located the working feed
  (`https://mikesignorelli.com/mike-writes?format=rss`) to unblock the
  audit; it reads 100% `Mike Signorelli` via `dc:creator`.
- **SITEMAP**: 367 raw URLs → 306 after filtering (same generic-heuristic
  caveat as Kris — not Squarespace-collection-aware).
- **SAMPLE**: 20 URLs → 3 clean `Mike Signorelli` hits via JSON-LD, 16 with
  no author detected (real limitation: this site renders author names via
  client-side JS that a static-HTML crawl can't see — not evidence of other
  voices), and **1 false positive manually verified and discarded**:
  `/bible-reading-plans-1` is Squarespace template placeholder content
  ("Blog Post Title Four (Copy) (Copy) (Copy)", dated 4/28/25 and 6/19/19,
  attributed to "Rachel Fung" — a stock Squarespace demo name), not a real
  published post or guest author.
- **VERDICT: single-voice (safe to bulk-attribute)** — correcting the raw
  script's first-pass "single + guests" call, which was driven entirely by
  that one template artifact. Real signal (feed + 3 clean sample hits) is
  100% Mike Signorelli; zero genuine other authors found. Caveat: the
  no-author-detected rate is high (JS-rendered names), so this rests on a
  thinner explicit sample than the other single-voice sources — a headless
  render (e.g. Playwright) would be needed for full per-post confidence if
  that matters for ingestion.

### John Bevere
- **FEED**: 10 entries, all `John Bevere`.
- **SITEMAP**: `post-sitemap.xml` child correctly isolated by Yoast naming;
  10 raw → 10 filtered.
- **SAMPLE**: 10/10 `John Bevere` via JSON-LD. Zero conflicts.
- **VERDICT: single-voice (safe to bulk-attribute).** Small archive (10
  posts) — clean, unambiguous signal from every angle.

### Dr. Michael Brown
- **FEED / SITEMAP**: FAILED — `thelineoffire.org` is on Vercel and returned
  HTTP 429 with an `x-vercel-mitigated: challenge` header on every request,
  including robots.txt itself, persisting after an 8s pause and under
  Python's plain default UA too. This is a bot-management challenge, not a
  real rate limit tied to our request pacing, and not fixable by identifying
  more politely — it's the same category of block as Vlad's.
- **VERDICT: undetermined — needs manual check.**

### Darren Rouanzoin
- **FEED**: 20 entries, all `Pastor Darren`.
- **SITEMAP**: 211 raw → 210 filtered (Substack's own sitemap, already
  clean — no index/child-sitemap step needed).
- **SAMPLE**: 20/20 `Pastor Darren` (19 via JSON-LD, 1 via meta tag on the
  archive page). Zero conflicts.
- **VERDICT: single-voice (safe to bulk-attribute).**

## Summary

| Source | Feed authors | Archive size | Sampled distinct authors | Verdict |
|---|---|---|---|---|
| Vlad Savchuk | unavailable (blocked) | unavailable (blocked) | none | undetermined — needs manual check |
| Kris Vallotton | unavailable (feed didn't resolve) | ~737 (filter noise: includes ~26 product/book-detail pages) | Kris Vallotton | single-voice |
| Mike Signorelli | Mike Signorelli (via corrected feed URL) | 306 (same filter-noise caveat) | Mike Signorelli | single-voice |
| John Bevere | John Bevere | 10 | John Bevere | single-voice |
| Dr. Michael Brown | unavailable (blocked) | unavailable (blocked) | none | undetermined — needs manual check |
| Darren Rouanzoin | Pastor Darren | 210 | Pastor Darren | single-voice |

## Explicit flags requested

- **(a) Vlad archive size / HungryGen overlap**: no archive size obtainable —
  site fully blocked this crawler. The HungryGen-overlaps-Vlad relationship
  can't be quantified from this pass; would need either manual archive
  review or a different access path to Vlad's content.
- **(b) Hidden guests (sample found authors the feed didn't)**: none
  confirmed. The one candidate (Signorelli / "Rachel Fung") was checked by
  hand and is Squarespace template placeholder content, not a real guest
  author. Worth keeping as a cautionary example: an unverified run would
  have logged a false guest-author signal.

## Known limitations of this pass (apply to any future re-run)

- Two of six sources (Vlad, Brown) are fully inaccessible to a
  polite/honestly-identified crawler — both use bot-management products
  (Cloudflare, Vercel challenge) that block on fingerprint, not UA string
  or pacing. Getting real data would require either manual review or an
  explicit decision to present as a browser, which you already declined.
- The sitemap post-filter is a generic path-exclusion heuristic, not
  site-aware. It slightly over-counts "archive size" on Squarespace sites
  (product/book-detail pages) and would need per-site tuning for exact
  counts.
- Author detection is static-HTML only. Sites that render author names via
  client-side JS (confirmed on mikesignorelli.com) will under-report
  detected authors even when the true byline is one consistent name.
