# Position layer foundation — Phase 4 opening session

**Date:** 2026-07-28
**Session type:** Build + live database write (new tables and new rows only). Per CLAUDE.md's Session Routing table, ran on the plain/psycopg2 path — never the harness — because the session performs schema DDL and INSERTs against Supabase.
**Scope:** storage, the generation path with its structural guarantees, and proof on one teacher. No serving change — nothing users see is different after this session.
**Author:** Claude Code, proposing for Alex's decision. CLAUDE.md, PLAN.md, and rhemata-status.md are untouched — Alex decides what to fold in after reading this.

---

## Flag before anything else: the eligibility input has a caveat worth reading

This session's hard rule was to use the "pass both" set from `docs/audits/statement_recheck_closeness_citation_2026-07-28.md` as the only eligible evidence for position generation. Two things worth surfacing about that set before trusting it blindly:

1. **PLAN.md's own #47 entry says that report's citation-check half is not fully closed**: *"closeness-check half is sound; citation-check half is NOT, per #45.6's scanner finding. Must be re-run after #45.6's Pattern-A gap is fixed before this item can be considered closed."* The scanner in question over-counts fabrication — it misreads genuine spoken-form citations ("Acts chapter 20 and verse 31") as fabricated. This is the same defect an earlier session in this conversation independently confirmed at length in `docs/audits/reference_grounding_dry_run_2026-07-28.md` (33 of 39 sampled strips were genuine references wrongly dropped).
2. **This does not make the "pass both" set unsafe to use, though — it makes it conservative.** Over-counting fabrication means some genuinely fine statements get wrongly excluded (sent to "needs fixing" instead of "pass both"); it does not let anything bad *into* "pass both." The residual risk that *does* still apply is the original, already-disclosed one: under-counting (a fabrication the compact-citation scanner can't parse at all, or a bare-attribution fabrication like the "Devil's Voice" case, which has no reference to check in the first place). That risk existed for the whole corpus before this session and is unchanged by anything built here.

Net: using this set was reasonable and is what Alex's brief explicitly directed. Flagging it here rather than silently proceeding, per CLAUDE.md's "surface risks before building, not after."

**A second, related finding: the eligible set as re-derived live today is 2,069 propositions, not the report's 2,067.** `scripts/eligible_statements.py` reproduces the report's exact bucket definition (closeness PASS and citation `pass`/`no_references`) using the checks as currently committed. Re-running found 2 more eligible propositions than the report — fully explained, not a mystery: commit `ee267d4` (BOOK_MAP ordinal/spelled/Roman-numeral fix) landed *after* the 2026-07-28 report ran, in the same day's session. Two propositions whose source text cited scripture using a form like "1st Samuel" were unrecognized by the source-side scanner under the pre-fix book-name map, so their citation read as a false failure; with the fix live, both now correctly resolve as grounded. Verified directly: the `uncertain` count is unchanged at 5 (matches the report exactly — that bucket traces to an unrelated, still-open dotted-abbreviation defect), while `fail` drops from 64 to 62 and `pass` rises from 573 to 577 — exactly the shape of 2 citations moving from fail to pass, nothing else shifting. **This session used the live, re-derived 2,069-ID set**, computed fresh by `scripts/eligible_statements.py` and enforced by explicit ID set at every evidence-gathering call — not the frozen 2,067, and not by assumption.

---

## Step 1 — Schema

Two new tables, additive only, nothing else touched (`migrations/073_positions.sql`):

**`positions`** — one row per generated teacher-specific position:

| Column | Purpose |
|---|---|
| `kind` | `text NOT NULL DEFAULT 'teacher' CHECK (kind = 'teacher')` — see "Guarantee: corpus-wide is refused" below |
| `source_id` | `NOT NULL REFERENCES sources(id)` — which teacher |
| `topic` | the topic/question this position answers |
| `content` | the position text |
| `status` | `draft` / `approved` / `stale` / `retracted` — lifecycle, defaults to `draft`; nothing this session is `approved`, that's a future human step |
| `prompt_version`, `prompt_fingerprint`, `model` | provenance, all `NOT NULL` — see "Guarantee: provenance" below |

**`position_evidence`** — one row per (position, proposition) pair: real, queryable evidence, not a prose mention or a `text[]` column of IDs. `proposition_id` is `ON DELETE RESTRICT` (not `CASCADE`) — deliberately: if a proposition a position depends on is ever deleted, that delete must fail loudly and force a human decision about the position, never silently shrink its evidence out from under it.

Both tables: RLS enabled, service-role-only policy (mirrors `teacher_profiles`, migration 064 — no public-read policy yet, since nothing user-visible reads these tables this session).

Applied via psycopg2 directly (not MCP — `guard_pretooluse.py` denies MCP writes regardless), verified on a **fresh** connection afterward: `to_regclass('public.positions')` / `to_regclass('public.position_evidence')` both resolve, full column/constraint listing matches the migration exactly, both tables start at 0 rows.

---

## Step 2 — Guarantees, and how each is structurally enforced

**Generation cannot receive source/chunk text.** `generate_position_text(teacher_name: str, topic: str, evidence: List[dict])` in `scripts/positions.py` is the only function that calls the LLM. Its evidence items are `{"id", "content"}` pulled from `propositions.content` only. The function opens no database connection, imports nothing that reads `chunks` or `documents`, and has no `document_id`/`source_id` parameter — there is no argument through which source text could reach it. This is a signature-level guarantee, not a prompt instruction telling the model to ignore something it was handed. The one function that *does* touch the database, `gather_evidence()`, `SELECT`s only from `propositions` (never `chunks`) and hands the generator nothing but that table's `content` column.

**Corpus-wide is refused twice.** `write_position()` raises `ValueError` before ever opening a transaction if `kind != "teacher"` — application-level gate. The `positions` table's own `CHECK (kind = 'teacher')` constraint (migration 073) would reject the `INSERT` even if that application gate were bypassed or forked entirely. Widening either requires a deliberate code change or a future migration that changes the constraint — not a runtime flag.

**Honest-empty floor.** `write_position()` checks `len(evidence) >= MIN_EVIDENCE_COUNT` *before* calling the LLM at all — a refusal costs nothing beyond the (cheap) embedding call already spent gathering candidates. Proven live: the "infant baptism and the sacraments" topic gathered 0 eligible Savchuk statements and refused with `evidence_count=0 < min=5`, no LLM call made, nothing written. See the floor derivation below.

**Provenance.** `prompt_version`, `prompt_fingerprint` (SHA-256 of the raw instruction template, computed fresh every call — same authoritative-over-the-label design as `propositions.prompt_fingerprint()`), and `model` are `NOT NULL` on the `positions` table itself. Unlike `propositions.prompt_version` (nullable, which is exactly why all 2,409 live propositions have NULL provenance today per CLAUDE.md's Landmines), an unstamped write is impossible here at the schema level, not just discouraged by convention.

**Reused, not forked:** the position-generation call sends the same `get_guardrails_text()` theological-guardrails block every other LLM call that represents a source document's or teacher's views already sends (`chat.py`'s answer stream, `study.py`'s live teacher-card synthesis) — a position is held to the same standard as any other product surface that speaks in a teacher's voice, from its first row.

---

## Evidence-gathering and the floors, both grounded in real data

`gather_evidence()` embeds the topic (`text-embedding-3-small`, same model/dimensions as every proposition's own stored embedding — migration 051), then does a cosine-similarity search over `propositions` restricted to the teacher's own documents, filtered to the eligible 2,069 IDs and a similarity floor, capped at 15.

**`SIMILARITY_FLOOR = 0.4`** — chosen fresh for this retrieval shape, not reused from `study.py`'s `TEACHER_POSITION_SIMILARITY_FLOOR = 0.3`. PLAN.md #48 explicitly states that floor "was tuned for the current retrieval path and does not transfer" (it searches `chunks`, not `propositions`). A floor sweep against real Savchuk data justified 0.4:

| Topic | 0.3 | 0.4 | 0.45 | 0.5 |
|---|---:|---:|---:|---:|
| deliverance from demons and spiritual warfare | 50+ | 50 | 50 | 27 |
| how to pray effectively | 50+ | 50 | 41 | 9 |
| fasting | 37 | 26 | 23 | 16 |
| the rapture and end times | 50+ | 22 | 10 | 7 |
| church leadership structure and eldership | 50+ | 7 | 1 | 0 |
| predestination and Calvinist double election theology | 50+ | 4 | 1 | 0 |
| infant baptism and the sacraments | 17 | **0** | 0 | 0 |
| liturgical calendar and observing church holy days | 24 | **0** | 0 | 0 |

At 0.3, even topics genuinely absent from Savchuk's corpus return a full page of noise (17–24 "matches" for infant baptism, on inspection unrelated content like "abortion as ritual" scoring 0.36–0.39). At 0.4, real thin/absent topics separate cleanly from real dense ones. This is a reasoned starting point from one teacher's real data, not a multi-teacher calibration — flagged as provisional in `scripts/positions.py`'s own docstring, same posture the closeness-check floors had before their own human-calibration pass (#46).

**`MIN_EVIDENCE_COUNT = 5`** — the honest-empty floor itself (Step 2's actual requirement). At floor 0.4, genuinely dense topics cleared 20–50 statements; genuinely thin-but-real topics ("church leadership," 7; "predestination," 4) sat in the low single digits; genuinely absent topics returned 0. 5 sits just above that boundary: low enough not to block a real but narrow position, high enough that a position is never built from 1–2 statements (which would just be restating a single proposition, not synthesizing a position). Also provisional, also flagged as such.

---

## Step 3 — Proof on one teacher

**Teacher selection, verified by live query, not assumed.** The brief guessed Ravenhill "by share." Querying per-teacher counts *within the eligible 2,069 set* (not the whole corpus) found:

| Teacher | Eligible statements |
|---|---:|
| **Vlad Savchuk** | **898** |
| Leonard Ravenhill | 699 |
| Zac Poonen | 358 |
| Carter Conlon | 36 |
| Doug Kreighbaum | 16 |
| Derek Prince | 12 |

**Vlad Savchuk has the richest eligible coverage, not Ravenhill.** Proceeded with Savchuk — exactly the kind of assumption this session's brief told me to check rather than trust.

**Run: 4 topics, 3 written, 1 refused, 0 errors.**

```
attempted=4 written=3 refused_floor=1 errored=0
Reconciles.
```

### Example 1 — "deliverance from demons and spiritual warfare" (15 evidence statements)

> Vlad Savchuk teaches that Christians can have demons and need deliverance, pointing to biblical examples like Ananias and Jesus's statement that "deliverance is the children's bread." He emphasizes that biblical deliverance centrally involves commanding demons to come out, following Jesus's model in Mark 1:25 where He rebuked and commanded an unclean spirit to leave. Savchuk argues this power-encounter approach—directly confronting and casting out demons using Jesus's authority—is more effective than simply breaking off spirits or other methods.
>
> While affirming that deliverance is Jesus's ministry for setting captives free, Savchuk warns against common pitfalls: fearing man, demonizing everything, and failing to discern between demons, flesh, curses, and natural disorders. He stresses that not every issue is demonic—some problems are physical conditions or character issues—and proper discernment is essential before attempting deliverance. He rejects traditional teachings that hinder deliverance, such as the notion that Christians cannot have demons or that interrogating a demon constitutes improper conversation with it, insisting interrogation helps understand demonic influence.
>
> Savchuk teaches that the Holy Spirit's presence does not automatically expel demons; believers can still experience demonic influence if they open themselves to it through connections to witchcraft, idolatry, or other demonic doorways. He identifies demonic assignments including sexual impurity, relationship breakdown, bitterness, pride, unbelief, and spiritual deception. Believers must break agreements with the enemy, renounce lies, control their inputs and outputs, speak God's word, and resist negative thoughts. Savchuk emphasizes putting on God's armor rather than directly engaging territorial spirits, and reassures believers that witnessing deliverance is not dangerous and that Jesus's freedom is genuine and complete.

### Example 2 — "how to pray effectively" (15 evidence statements)

> Vlad Savchuk teaches that effective prayer centers on cultivating constant communion with God rather than treating prayer as religious duty. He emphasizes that prayer should be relational, not ritualistic—God desires genuine, heartfelt connection, not empty repetition as Jesus warns against in Matthew 6:7. Savchuk encourages believers to pray without ceasing by integrating short intervals of prayer throughout the day, maintaining connection with God amid busy schedules. He offers practical methods like "break" (breathing, reentering, asking, keeping listening, expressing thanksgiving) for praying while driving, helping believers realign with the Holy Spirit during daily commutes.
>
> Savchuk stresses balancing different prayer modes: mixing praying in tongues with praying with understanding, following Paul's model in 1 Corinthians 14:15. Growing in prayer language comes not through volume or emotion but by yielding to the Holy Spirit and building consistent private patterns, strengthening one's spiritual life as described in 1 Corinthians 14:4 and Jude 20. However, he insists that praying on the move should not replace dedicated, unhurried time alone with God, following Jesus' example in Matthew 6:6 and Mark 1:35.
>
> Effective prayer requires pure motives and submission to God's will rather than attempting to manipulate outcomes or force God's hand. Savchuk highlights prayer's role in spiritual warfare, where believers fight back against the enemy and grow stronger. He emphasizes developing a secret life of prayer, fasting, and giving as taught in Matthew 6, promising that the Father rewards what is done in secret.

### Example 3 — "fasting" (15 evidence statements)

> Vlad Savchuk teaches that fasting is abstaining from food to quiet the flesh and hear the Holy Spirit, allowing God to fill the emptiness created. He emphasizes that fasting is a biblical way of humbling oneself before God, with its purpose being to seek God's face rather than to diet or lose weight. Savchuk identifies different types of fasts: absolute fasts without food or water, normal fasts with only water, and the Daniel fast involving abstinence from certain foods. He presents fasting as preparation for new levels in God, pointing to Jesus, Paul, and Barnabas who fasted before entering new dimensions of ministry.
>
> Savchuk instructs that during a fast, believers should replace eating with reading God's word and let hunger remind them to pause and pray, deepening their connection with God. He teaches that fasting prepares believers for temptation by developing discipline in resisting wrong things. Jesus expected his followers to fast, saying "when you fast" rather than "if you fast," indicating it is a normal part of Christian life. Savchuk advises fasting in humility without seeking human applause, keeping it private unless accountability is needed. He notes that the Bible honors various fast lengths—from one day to forty days—and that fasting is more about heart and motive than specific hours, with most challenges being mental rather than physical.

### Refused (proof the floor fires)

"infant baptism and the sacraments" — 0 eligible Savchuk statements above the similarity floor. `write_position()` refused before any LLM call: `evidence_count=0 < min=5`. Makes sense: Savchuk is a charismatic/Pentecostal-register teacher who, on the evidence of his own eligible corpus, simply doesn't address a sacramental-tradition topic like infant baptism.

### Reading these as product text

All three read as a faithful, specific summary of one teacher's actual positions — not generic Christian consensus, not hedged, not averaged (trivially true here since evidence is single-teacher, but the text itself doesn't read like a committee wrote it either). They keep Savchuk's own distinctive framings ("deliverance is the children's bread," the "break" driving-prayer method, "when you fast" not "if you fast") rather than flattening them. Scripture references that appear (Mark 1:25, Matthew 6:6–7, 1 Corinthians 14:4/15, Jude 20) all trace to the underlying evidence statements, which are themselves drawn only from the pass-both eligible set — nothing here was independently checked against source text by this session (that's exactly the boundary the evidence-only design is meant to hold), but the propositions feeding it already cleared the citation-accuracy check.

---

## Step 4 — Reconciliation

**Hard counts:** attempted 4 / written 3 / refused_floor 1 / errored 0. `4 == 3 + 1 + 0` — reconciles.

**No existing rows touched, verified by fresh query, before and after:**

| Table | Before | After |
|---|---:|---:|
| `documents` | 3,595 | 3,595 |
| `propositions` | 2,409 | 2,409 |
| `sources` | 73 | 73 |
| `positions` (new) | — | 3 |
| `position_evidence` (new) | — | 45 |

**Per-position verification, fresh query, all 3 written positions:** exists, `kind='teacher'`, full provenance (`prompt_version`/`prompt_fingerprint`/`model` all populated), evidence row count matches what was generated (15 each), **every evidence proposition ID is in the eligible 2,069 set, and every evidence proposition belongs to Vlad Savchuk's `source_id`** — zero mismatches on either check, for all 45 evidence rows.

**Actual LLM cost this session:** 4 topic embeddings (`text-embedding-3-small`, ~10 tokens each — effectively free) + 3 `claude-sonnet-4-5` position calls (the refused topic never reached the LLM). Each call: system block (position instructions + guardrails text, ~700 words) + user message (15 evidence statements, ~1,500–1,800 words) ≈ 3,000–3,500 input tokens; output capped at 500 tokens, actual output ~350–400 words per position. Total for the session: roughly 10,000 input + 1,100 output tokens across 3 calls — at current Sonnet pricing, on the order of **$0.05–0.08 total**. Far under the $50 ceiling, as expected for a one-teacher proof.

---

## What's next (not decided here — Alex's call)

- **More teachers.** The mechanism is proven; running it against Ravenhill (699 eligible) and Poonen (358 eligible) next is mechanical, not a redesign. Savchuk's 898 leaves plenty of eligible statements for more topics on him too.
- **Floor calibration.** Both `SIMILARITY_FLOOR` and `MIN_EVIDENCE_COUNT` are reasoned starting points from one teacher's data, not a #46-style human calibration pass. Worth a dedicated look once more teachers' output exists to judge against, per PLAN.md #48's own note that the old teacher-card floor "does not transfer."
- **The serving path.** Nothing users see changed this session by design. PLAN.md #48 names the two leak surfaces this layer is meant to eventually close: the main chat answer path, and `study.py::get_teacher_card()`'s live per-request synthesis (which today embeds raw `chunks.content` into a live Anthropic call on every teacher-card open — the exact pattern this new layer's evidence-only design avoids). Wiring either to read `positions` instead is a separate, later session's scope.
- **Review/approval flow.** Every row this session wrote is `status='draft'`. Nothing here has been read and approved by Alex yet — that's the natural next step before anything downstream trusts these specific 3 rows, independent of the mechanism itself being sound.
