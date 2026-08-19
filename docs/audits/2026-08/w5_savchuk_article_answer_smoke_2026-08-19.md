# W5–W6 Answer-Integrity Smoke — Savchuk web article (2026-08-19)

## Outcome

**PASS.** Async `/async-chat` produced an `answered` job that retrieved and
cited the quarantined article, and the served prose tracks the article’s own
teaching without inventing Savchuk claims off other teachers’ citations.

## Method

- Question chosen to **avoid** `match_position_paper` → `speaking_in_tongues`
  (verified locally before submit):
  - `"How do I develop my prayer language in private?"` → `speaking_in_tongues`
  - `"What does Vlad Savchuk teach about developing a prayer language?"` → `None`
- Submit guest `POST https://rhemata-production.up.railway.app/async-chat/submit`
- Poll `answer_jobs` to terminal `done`
- Script: `scripts/smoke_w5_savchuk_article_answer_2026-08-19.py`
- Raw dump: `docs/audits/_w5_smoke_raw_2026-08-19.json`

## Job

| Field | Value |
|---|---|
| job_id | `94cf9284-be14-481c-8f4c-38e2c4fdb81c` |
| outcome | `answered` |
| policy_version | `policy_v3:quote_selection=true` |
| model | `claude-sonnet-5` (as stored on the job row) |
| retrieved chunks | 16 |
| citations | 9 |
| verified_references | 5 |
| quote_ids | `[]` (none selected — allowed) |

## Article presence

Document `c97533db-7b48-46ec-b77f-239b703b8697` /
source `33cfa6b5-…` **Vlad Savchuk (web staging)**.

| Check | Result |
|---|---|
| Article chunks in `retrieved_chunk_ids` | **2/4** — chunk 0 `3c7715a3-…`, chunk 1 `4b0853f9-…` |
| Article rows in `citations` | **2** — author `Vlad Savchuk (web staging)`, title `How to Grow in Tongues and Strengthen Your Prayer Language`, pastorvlad URL (Mailchimp suffix retained) |
| Prose names Savchuk | Yes (`According to Vlad Savchuk…`) |
| Prose contains `(web staging)` | No (clean display name in answer body) |

## Integrity read (answer vs article)

Served bullets map to article chunks 0–1 (and the KEEP-pattern claims from
eligibility review):

| Answer point | Article support |
|---|---|
| Yield / consistent daily practice, not trying harder | Chunk 0 opening |
| Not a spiritual badge; 1 Cor 14:4 → build-up | Chunk 0 |
| Scripture before feelings; 1 Cor 14:4, Jude 20, Acts 2:4 | Chunk 0 “Start with Scripture” |
| Consistent time/place; five minutes daily | Chunk 0–1 |
| Worship then tongues; Acts 10:46 | Chunk 1 |
| Yield your mouth; Acts 2:4 cooperative speaking | Chunk 1 |
| Pray through pressure; Romans 8:26 | Chunk 1 |

No answer bullet attributes Derek Prince / Ravenhill material to Savchuk.
Closing line (“drawn entirely from Vlad Savchuk’s teaching”) is slightly
strong relative to a mixed citation rail, but the **named claims** stay on
Savchuk’s article content. Ranked failure mode #2 (misrepresentation) not
observed on this sample.

## Retrieved pool (context)

Also retrieved (not attributed as Savchuk prose): live Vlad Savchuk YouTube
“How to Grow in the Gift of Tongues…”, Derek Prince tongue sermons, Ravenhill
clip, plus other prayer/Spirit background. Confirms the staging article sits
alongside the existing corpus, not instead of it.

## Residuals (not blockers for this smoke)

1. **Citation speaker label** still `Vlad Savchuk (web staging)` — known from
   write audit; optional rename still open.
2. **`verified_references` teacher pointer** for raw `"Vlad Savchuk"` resolved
   to the **live** Savchuk source `74ed5fa1-…`, not staging `33cfa6b5-…`.
   Expected given name matching; record only — does not undo citation rows.
3. Citation URL keeps the site’s Mailchimp tracking suffix from capture.
4. How-to / non-teacher-named prayer-language questions still match the
   `speaking_in_tongues` position paper; this smoke deliberately used the
   teacher-named phrasing so the article path could be judged without the
   house-fence empty-answer fallback.

## Acceptance vs PLAN.md W5–W6

- [x] Article-supported async answer completes
- [x] Article document appears in retrieval + citations
- [x] Answer claims track the article (spot integrity read)
- [ ] Optional staging display-name rename — still open, not required to close
      the residual checkbox
