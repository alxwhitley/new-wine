# Position-layer topic list V1 (Open Decision #16)

**Date:** 2026-08-06/07  
**Decision owner:** Alex  
**Scope band:** Seed only (Alex's pick this session)  
**Status:** **ADOPTED as the V1 closed set** — unblocks design/build of
`match_stored_position()`; does **not** itself build matching or injection.

## What this list is

The hand-authored, closed set of topics for which a stored `positions` row
(teacher or corpus) may be matched at question time so its underlying
**propositions** can feed the one-hop answer path (never the position's
rendered text — CLAUDE.md item 18 revision).

This is **not**:

- hundreds of thousands of pre-answered questions (forbidden by Settled #1)
- a teacher taxonomy (forbidden by Settled #7 / Invariant 13)
- a replacement for position **papers** (house fence — separate mechanism)
- automatic expansion from corpus majority (corpus majority ≠ house view)

## Matching posture (for the next build session)

Reuse the proven discipline from `match_position_paper()` / `debate_topics.py`:

- Closed registry of topic keys
- Short, hand-picked phrase lists (lowercase substring)
- Avoid bare single words that over-trigger
- Fail direction: **no match → normal retrieval** (never invent a position)
- Near-tie / multi-match: refuse match until resolved (same spirit as paper
  registry near-tie handling)

`topic_key` normalization stays `normalize_topic_key()` in
`scripts/positions.py` (must match migration 077 SQL).

## V1 topics (exactly these six)

Live `positions` rows with `is_current=true` as of 2026-08-06/07 query — these
are the only topics with existing evidence packs ready for one-hop wiring
once matching + review exist.

| # | `topic_key` (stored) | Current scope | Starter phrase anchors (draft — calibrate at matcher build) |
|---|---|---|---|
| 1 | `fasting` | teacher | "fasting", "how to fast", "why fast", "biblical fast", "fast and pray" |
| 2 | `deliverance from demons and spiritual warfare` | teacher | "deliverance", "spiritual warfare", "cast out demons", "demonization", "demonic oppression", "casting out demons" |
| 3 | `how to pray effectively` | teacher | "how to pray", "effective prayer", "prayer life", "intercession", "how should i pray" |
| 4 | `the divine exchange at the cross` | teacher | "divine exchange", "exchange at the cross", "jesus took our", "great exchange", "what happened at the cross" |
| 5 | `can a believer lose their salvation` | corpus | "lose salvation", "lose their salvation", "eternal security", "once saved always saved", "can a christian fall away", "perseverance of the saints" |
| 6 | `holiness and personal purity` | teacher | "holiness", "personal purity", "sanctification", "holy living", "walk in holiness", "set apart" |

**Note on #6 / sanctification:** Settled decision #11 explicitly says
sanctification models is **not** a debate topic. Including `holiness and
personal purity` here is consistent with that — ordinary topic, not a
standing multi-teacher debate stitch.

## Explicitly OUT of V1

| Category | Why out |
|---|---|
| **Debate topics** (decision #11): healing mechanics, prophetic accountability, apostolic authority, eschatological timing | One-hop positions must not quietly freeze one corpus majority as "the" answer on open debates |
| **House pillars with live papers only** (baptism_holy_spirit, speaking_in_tongues) | Already fenced by position papers; no current `positions` row for one-hop evidence injection. Do **not** double-route via this list until a deliberate positions build + review for those topics |
| **Draft papers not yet registered** (deliverance draft, divine healing, five-fold, gifts, prophecy, prosperity) | Papers ≠ positions; healing/five-fold/prophecy overlap debate list anyway |
| **Everything else** | Unmatched → normal RAG; grow the list only by deliberate addition after real traffic or Alex's call |

## Relationship to other classifiers

| Mechanism | Role | Overlap with this list |
|---|---|---|
| `debate_topics.py` | Debate vs settled for single-teacher lock | Debates stay out of V1; tongues settled is paper path, not this list |
| `position_papers.py` PILLARS | House fence + exclusion | Baptism/tongues stay paper-only for V1 |
| `positions` table + one-hop | Proposition evidence packs for matched topics | **This list** |

If a future question matches both a debate phrase and a V1 topic phrase,
**debate wins** (fail safe: do not inject a stored position on a debate topic).

## What this does **not** authorize yet

- Building or serving one-hop injection (still PLAN sequence: matcher →
  review workflow → adapter → concurrency → inject → rollout)
- Auto-generating positions for new topics
- Expanding beyond these six without updating this document and PLAN.md #16

## Next engineering step (not this session)

1. Implement `match_stored_position(question) -> Optional[topic_key]` against
   this registry (phrase lists refined live against false-positive tests).
2. Prove it only fires on the six keys and never on debate-phrase questions.
3. Then continue the one-hop build sequence from the 2026-08-04 diagnostic.

## Provenance

- Live DB current positions: fasting; deliverance from demons and spiritual
  warfare; how to pray effectively; the divine exchange at the cross; can a
  believer lose their salvation; holiness and personal purity
- Scope band: Alex "Seed only" 2026-08-06/07
- Design: `docs/audits/position_layer_revival_diagnostic_2026-08-04.md` §7
