# Position Paper serving path — baptism_of_the_holy_spirit demo — 2026-07-30

**Plain-English summary:** The demo worked end-to-end. When someone asks a question about the baptism of the Holy Spirit — even worded completely differently from the source document — Rhemata now recognizes the topic and answers using Alex's own hand-written teaching on it, speaking in its own voice with no citation, no disclaimer, and nothing telling the user a written document is behind the answer. Off-topic questions, including a deliberately tricky one about a totally different kind of baptism (water baptism), correctly get ignored by this new path and still go through the normal answer-generation process untouched. One thing was caught and fixed during testing before it shipped — the matcher would have also fired on water-baptism questions — and one small cosmetic issue was found and, at Alex's direction, left as a known, documented imperfection rather than fixed this session (roughly 1 in 3 of the broadest test answers occasionally echoed one section heading from the source instead of writing fresh wording, even though the substance and all the required disclosure rules were fine every single time). Nothing has been committed to git yet — the code is built, tested against real API calls, and reviewed, and is waiting on Alex's go-ahead to commit.

---

## What was built

**New file:** `backend/app/services/position_papers.py` (333 lines) — a topic matcher plus a dedicated answer generator, scoped to exactly one document.

**Edited file:** `backend/app/routers/chat.py` — one new import line, plus a 53-line early-return block inserted at the very start of the request handler (before any retrieval work runs). If the new matcher fires, the entire normal pipeline — query expansion, vector/FTS search, Cohere rerank, citation building, the normal system prompt — never runs at all for that request. If it doesn't fire, every line of the existing handler runs exactly as it did before this session; nothing else in `chat.py` was touched.

### How topic-matching works

Each incoming question is compared (via OpenAI embeddings, one call per question) against two cached reference points: the paper's title and a short description of its content. A question matches only if it's similar enough to those AND more similar to them than to a third cached reference point representing water baptism — a deliberately different sacrament that the first version of the matcher confused with this topic.

This threshold and the water-baptism safeguard were both found empirically, not guessed: 8 realistic paraphrased questions (half of them sharing no wording at all with the paper's title, e.g. "How can I be filled with God's power for ministry?") were tested against 7 different-topic questions (teacher-citation questions, core-doctrine questions, and two water-baptism questions) using the real embeddings API. The gap between the weakest real match and the strongest false match was wide enough to set a safe threshold.

### How the answer is generated

The paper's content is read live from the database (the same `chunks` table the app already uses for storing ingested documents — not a static copy), fed to a dedicated instruction set that forbids citing sources, forbids naming Alex or "this document," forbids the phrase "position paper," and forbids the "Rhemata can make mistakes" disclaimer (that disclaimer belongs to a different, unrelated fallback feature). The model then writes a fresh, conversational answer tailored to the actual question asked, rather than reciting the source's section headings in order.

## Test results

- **8/8 realistic paraphrase questions** correctly matched and produced clean answers (verified against the real Anthropic API, not mocked) — no citation markers, no attribution, no "position paper" label, no disclaimer, no truncation, on every single run.
- **7/7 clearly-different questions** — including two Derek Prince teacher-citation questions, three core-doctrine questions, and two water-baptism questions — correctly did NOT match, and were confirmed (by reading the code) to fall through to the completely normal answer path untouched.
- Scripture references in two sampled answers were checked against the source paper — no fabricated references found.
- Proof that the new path actually ran (not just "an answer came back with no errors"): the real API call payload was captured and confirmed to contain the dedicated instructions and the real paper content, not the normal citation-mode prompt.

## Decisions made this session (things I brought to Alex rather than deciding silently)

1. **The water-baptism false-match risk**, found during calibration testing before any code was written. Alex chose to fix it now (adding the third "contrast" reference point described above) rather than ship with the known gap.
2. **A production-deployment gap**, found during testing: the first version read the paper directly from a file on disk, but that folder isn't included in what gets deployed to the live backend — so the feature would have silently done nothing once actually deployed, without breaking anything else. Alex chose to fix this now by switching to a live database read (the same approach already used elsewhere in the app for similar content) rather than deferring it.
3. **The occasional section-heading echo** on the single broadest test question. Alex chose to accept this as a known, disclosed cosmetic limitation rather than have more engineering effort spent chasing it — the substantive requirements (no citation, no attribution, no disclaimer, no label) passed every time regardless.

## What's disclosed as a known, accepted limitation (not blocking, by Alex's decision)

- On the broadest possible test question ("What is the baptism of the Holy Spirit?"), roughly 1 in 3 runs echoed one of the source paper's own section headings ("How to Receive") as a bold label in the answer, instead of writing fresh wording, despite the instructions explicitly forbidding this. Narrower, more specific questions never showed this. This is a wording/polish issue only — it does not leak that a written document exists, does not cite anything, and does not affect any of the hard requirements.
- Reading the paper's content from the database rather than the raw file introduces a small amount of duplicated text at the seams where the document was originally split into chunks (roughly 18% of the total length is repeated boundary text, not missing or wrong content — just repeated). This is the same pattern the app already uses elsewhere for similar content and did not visibly affect answer quality in testing (all 8 positive tests were clean, well-formed, and not truncated). Left as-is; a future cleanup could de-duplicate it if anyone wants to.

## What needs a decision before scaling to the other pillars

- **The one-paper scoping is deliberate and load-bearing — not just a placeholder.** The code is explicitly written to serve only this one document; nothing about it generalizes automatically. Each additional pillar (speaking in tongues, healing, deliverance, prophecy, etc.) needs its own calibration pass (its own realistic paraphrase/negative test set) before being wired in the same way — the threshold and contrast anchors found this session are specific to this one topic's semantic neighborhood, not a universal setting.
- **The topic-candidate-tracking/growth-mechanism logging** (which future topics get written as a Position Paper next, based on real usage) was explicitly out of scope for this session and still needs to be built before or alongside scaling — without it, there's no data-driven way to decide which pillar to write next.
- **The section-heading-echo residual**, if it recurs across future pillars' broadest questions, may be worth a more deterministic fix at that point (a filter over the output rather than more prompt wording, which was already shown this session not to reliably reach zero).

## Files touched

- `backend/app/services/position_papers.py` — new file, 333 lines.
- `backend/app/routers/chat.py` — edited: 1 import line + 53-line early-return block added; nothing else changed.

## Commit(s)

**None yet.** Per this repo's standing rule, code commits are Alex's own action after reviewing the diff — nothing has been committed this session. Waiting on Alex's go-ahead.

---

## Technical detail for reference

- **Session type:** Repo-only multi-step build (CLAUDE.md Session Routing) — harness path, `executor`/`planner-reviewer` two-agent loop. Zero database writes for the entire session (verified repeatedly by grep for mutation methods and by testing every function in isolation rather than through the live metered `/chat` endpoint, whose usage-counting RPCs and conversation-save are real writes).
- **Calibration numbers (Phase A, before the contrast-anchor fix):** anchor representation = max cosine similarity across `"Baptism of the Holy Spirit"` (title) and a short synthesized description of the paper's "What It Is" section, against OpenAI `text-embedding-3-small`. Lowest qualifying positive: 0.3739 ("What did Jesus mean by being clothed with power from on high?"). Highest clearly-different negative: 0.2785 ("What is the unpardonable sin?"). Gap: 0.0954, clearing the ≥0.05 margin set as the pass condition. `MATCH_THRESHOLD = 0.3262` (the gap's midpoint).
- **Contrast-anchor fix (Phase B, added after the water-baptism false-positive was found):** a third cached anchor, `CONTRAST_WATER_BAPTISM` — a short description of water baptism as a sacrament (immersion vs. sprinkling, believer's vs. infant baptism). A question now only matches if `pos_sim >= MATCH_THRESHOLD and pos_sim > contrast_sim`. Verified against the real API: all 8 original positives still clear both conditions (smallest margin ~0.148); both water-baptism test questions ("How should water baptism be performed?" and "Should infants be baptized?") now correctly fail the contrast comparison and return no match.
- **`position_papers.py` public surface:** `PAPER_KEY = "baptism_holy_spirit"`; `PAPER_DOCUMENT_ID` (the already-ingested `documents.id` this paper lives at); `match_position_paper(question: str) -> Optional[str]`; `POSITION_PAPER_VOICE_SYSTEM` (the dedicated system prompt, deliberately separate from `chat.py`'s normal `ANSWER_SYSTEM_BLOCKS`); `get_paper_body() -> Optional[str]` (lazy-cached, reads `chunks` table for `PAPER_DOCUMENT_ID` ordered by `chunk_index`, read-only `SELECT`, no mutation methods anywhere in the file); `generate_position_paper_answer(question, messages=None) -> Iterator[str]` (streams `_sse()`-formatted token events from a real streaming Anthropic call; no `<answer>` tag parsing, since this dedicated prompt doesn't use that wrapper).
- **`chat.py` wiring:** `matched_paper_key = match_position_paper(request.question)` is the first statement inside the existing `try:` block (before the code comment `# Step 0`). On match, returns a `StreamingResponse` whose generator streams tokens, reuses the existing `_save_conversation()` function unmodified (not forked) for authenticated users with `citations=[]`/`verified_references=[]`, and emits a final meta event with empty `citations`/`verified_references`, no `topics_established` key, and `usage` preserved when present. On no-match, `matched_paper_key` is falsy and every subsequent line runs completely unchanged from before this session.
- **Scope discipline confirmed by inspection:** `sources/documents/speaking_in_tongues.md` untouched; no topic-candidate-tracking/logging code added; the pre-existing `background_topics` table/mechanism (migration 030, `_ensure_background_topics()`/`match_background_topics()` in `chat.py`) is completely unmodified and remains live for the other two topics it already covers (`speaking_in_tongues`, `gift_of_prophecy`) — it is simply never reached for baptism-topic questions the new matcher catches first, since the new interception returns before that code executes.
- **License-gate safety:** the module's own docstring hard-warns against generalizing this into a "serve any `silent_context` document directly" mechanism — it is bound to exactly one `PAPER_DOCUMENT_ID`, which is safe specifically because this is Alex's own first-party owned house content (CLAUDE.md Invariant 7's `silent_context` serving posture), not arbitrary retrieved material.
- **Review process:** two full `executor`/`planner-reviewer` cycles (harness path per CLAUDE.md Session Routing). Planner-reviewer independently re-verified the calibration math, the actual git diff (not just the prose description), grep-confirmed zero mutation calls in the new module, and dynamically confirmed (via a captured real API call payload) that the dedicated prompt path actually executes on a match rather than trusting "an answer came back." Final verdict: **APPROVE**, both post-Phase-A and after the contrast-anchor + chunk-table-loader changes.
- **Existing pattern reused, not forked:** the chunk-table read for the paper body uses the identical join pattern (`"\n\n".join(c["content"] for c in rows)`) already live in `chat.py`'s `topics_to_inject` loop (~line 650) for the other two background topics — including the same chunk-boundary-overlap duplication quirk that pattern already has in production today. Not a new defect introduced this session.
- **Cost:** roughly 20-30 real OpenAI embedding calls (single-digit cents) plus roughly 16-20 real Anthropic completion calls across calibration and testing — well under any cost-review threshold.
