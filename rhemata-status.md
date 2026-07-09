# rhemata-status.md

**As of:** 2026-07-09 · terminal-owned · **overwritten each session, not a log** (append-only history lives in the Notion Rhemata row's Session Log).

**Source of truth by domain:** durable architecture/decisions → `CLAUDE.md` · messaging/positioning → `POSITIONING.md` · styling tokens → `DESIGN.md` · **this file → live state only, nothing durable, nothing "how it works."**

---

## Current Priority / Next Action

- **Current priority:** Chokepoint conversion is checkpointed (loss-prevention done); nothing else proceeds until the honesty fix lands, per plan.md's ordering.
- **Next action:** plan.md **#2 — Honesty fix**. Rewrite `POSITIONING.md` + `docs/how-rhemata-handles-sources.md` to the real posture (paraphrase-and-cite; quotes are a gated future surface, not a live guarantee), and remove `system_prompt.txt:112`'s permission to quote ≤50 words. One commit set.

---

## Where We Are in the Roadmap

(Notion `plan.md` v5.1, linear numbered session list)

- **#1 Back up `sources/` + `ingest_queue.xlsx`** — DONE this session (Alex confirmed offsite upload to Google Drive).
- **#1.5 Commit the uncommitted working tree** — DONE this session (commit `72476b7`, pushed to `origin/main`). Includes migration `058_clf_aliases.sql`, committed for the record — it was already applied live in production but had never been committed until this checkpoint.
- **#2 Honesty fix** — NEXT, not started.
- **#3 Verify the chokepoint conversion actually works** — not started.
- **#4–37** — untouched.

Notion's row snapshot (Current Priority / Next Action fields) has not been told about #1/#1.5 completing yet — this file is currently ahead of Notion on that point.

---

## In Progress / Uncommitted Locally

- `CLAUDE.md` — modified, uncommitted. Still carries the false "chokepoint shipped" claim; correction is plan.md #14, deliberately held out of recent commits until the conversion is actually verified (#3).
- `DESIGN.md` — modified, uncommitted. This session's theme-doc fix (dark-only correction, retired light tokens deleted) — diff shown to Alex, awaiting commit approval.
- Everything else clean as of commit `72476b7`.

---

## Open Blockers Awaiting a Decision

- Two sentinel-assigned docs ("So Great a Salvation," "The 59 One Another's of the NT") carry no author/source metadata — need Alex's eyeball, not resolvable from data alone (plan.md #6).
- Un-ingested `8.21.24 Prophetic Teaching - Prophetic Ministry.docx` — content read, no byline found in the extracted text; unconfirmed whether this is "the Bedford docx" plan.md refers to.
- `PRODUCT.md` (2026-06-14, oldest doc in the repo) overlaps `POSITIONING.md` (2026-07-02) — unclear if still authoritative or a superseded draft; needs Alex's call.
- Offsite backup of `sources/` + `ingest_queue.xlsx` — Alex confirmed uploaded to Google Drive; could not be independently located/verified from this Mac (not visible in any local CloudStorage mirror at time of check). Real but unverified.
- `SKILL.md` may carry the same false "chokepoint shipped" claim `CLAUDE.md` does — flagged, not yet checked line-by-line.

---

## Live Corpus & Infra Snapshot

(queried live, 2026-07-09)

- **Documents:** 3,796
- **Sources:** 67 total — 39 `unlicensed` / 26 `public_domain` / 2 `owned` / 0 `licensed`
- **Chunks:** 197,169
- **Propositions:** 2,028 (all from short-form content; zero full-length books extracted yet — first real test lands at plan.md #17)
- **`book_quotes`:** 0 rows (table retired per plan.md v5 decision; new verified-only quotes table not yet built)
- **Sentinel-assigned docs:** 3
- **Staging Supabase:** none exists — production DB only, no backup/PITR automation found in-repo.

---

## Next Session Should

Run plan.md **#2 — honesty fix**: rewrite `POSITIONING.md` + `docs/how-rhemata-handles-sources.md` to the real posture, and remove `system_prompt.txt:112`'s quote permission. Stop condition: no live claim of a verifier that doesn't exist.
