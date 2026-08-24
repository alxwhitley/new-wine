# Darlene Cunningham URL verification — 2026-08-24

Completes the deferred check `docs/audits/2026-08/discovery_suspect_url_verification_2026-08-19.md`
left "out of scope, noted in passing." Read-only web fetch only; no
spreadsheet or database write occurred.

## Darlene Cunningham — VERDICT: wrong person, do not ingest

- `claimed_main_url` (Discovery tab): `https://darlenecunningham.com/`
- Fetched directly: this is the professional author site of a **living indie
  romance novelist** — book listings (urban romantasy, dark romance, sports
  romance, with content warnings), merchandise, TikTok/YouTube/Patreon/
  Instagram/Facebook links. Footer: "© 2023 by Darlene Cunningham. Powered
  and secured by Wix." Site itself states it "will be shutting down
  permanently in November."
- **Zero reference to YWAM or any ministry affiliation anywhere on the site.**
  This is not the Darlene Cunningham the ingestion candidate presumably means
  (YWAM co-founder, Loren Cunningham's widow) — it is a same-name, unrelated
  private individual.
- This is a worse failure mode than the Reinhard Bonnke row (expired-cert,
  merely unreliable): ingesting from this URL would not just be low-quality,
  it would misattribute an unrelated living person's commercial fiction work
  under the "Darlene Cunningham" name in the corpus.

## Action needed (not taken here — read-only check only)

- Mark this Discovery-tab row's `claimed_main_url` as confirmed wrong/
  unusable before any promotion to the Queue tab.
- If Darlene Cunningham (YWAM) content is still wanted, source from
  `ywam.org` or the official YWAM/Cunningham-family channels already
  identified as authoritative in the Loren Cunningham check (`ywam.org`,
  `kb.ywam.org`), not a bare personal-domain guess.
- This closes CLAUDE.md's Landmines note that Darlene Cunningham's URL
  pattern was "flagged in passing" and unchecked — now checked, verdict is
  negative, not merely unverified.
