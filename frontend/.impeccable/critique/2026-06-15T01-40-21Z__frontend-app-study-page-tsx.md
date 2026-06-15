---
target: frontend/app/study/page.tsx
total_score: 26
p0_count: 0
p1_count: 0
p2_count: 3
p3_count: 2
timestamp: 2026-06-15T01-40-21Z
slug: frontend-app-study-page-tsx
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Loading skeletons everywhere; verseError lacks role="alert"; no save/flag confirmation |
| 2 | Match Between System / Real World | 3 | Theological vocabulary appropriate; dual-mode search not signaled |
| 3 | User Control and Freedom | 3 | Arrow key nav, back from commentary, sheet dismiss; exiting word study mode not obvious |
| 4 | Consistency and Standards | 2 | Hamburger missing aria-label; top bar missing border-b; verseError missing role="alert" |
| 5 | Error Prevention | 3 | Book autocomplete, word dropdown, disabled boundary arrows |
| 6 | Recognition Rather Than Recall | 2 | No guidance on dual-mode search; interlinear discoverable; word study mode opaque |
| 7 | Flexibility and Efficiency | 3 | Arrow key verse navigation is a genuine power-user feature; no search focus shortcut |
| 8 | Aesthetic and Minimalist Design | 3 | Single-column, anchor nav, inline expansion — well-organized for the content density |
| 9 | Error Recovery | 2 | verseError visible; no role="alert" for SR; no retry; commentary empty state gives no next step |
| 10 | Help and Documentation | 2 | Placeholder is the only guidance; dual-mode undiscoverable |
| **Total** | | **26/40** | **Acceptable** |

## Anti-Patterns Verdict

**LLM assessment**: No slop. Interlinear tap-a-word → definition → library results → word study is genuinely differentiated. No reflex patterns. One tell: uppercase tracked section labels appear 5+ times; functional in a research tool but the saturation matches the ban pattern.

**Deterministic scan**: detect.mjs → [] — clean. Manual review caught: prose-sm + max-w-none at line 661 (DESIGN.md violations); border-l-2 on blockquote at line 293 (borderline absolute ban).

## Overall Impression

Most sophisticated page in the app. Interlinear Bible study experience is genuinely differentiated. Content density is high by necessity; anchor nav handles it well. Chief gap is consistency with the rest of the app (aria-label, border-b, role="alert" all missing on this page). Prose-sm violation and undiscoverable dual-mode search are the next tier.

## What's Working

1. **Arrow key verse navigation** — genuine power-user feature wired correctly with input tag guard.
2. **Inline word panel vs. mobile bottom sheet** — right affordance for each context.
3. **Book autocomplete + word search disambiguation** — same input handles three modes elegantly.

## Priority Issues

**[P2] Three consistency gaps with the rest of the app**
Top bar (line 1316): missing border-b border-border. Hamburger (line 1318): missing aria-label="Open sidebar". verseError (lines 1372, 1540): missing role="alert" aria-live="polite".
Fix: Add border-b border-border to top bar div; aria-label="Open sidebar" to hamburger; role="alert" aria-live="polite" to both verseError elements.
Command: /impeccable polish

**[P2] prose-sm and max-w-none in word study Sheet**
Line 661: "prose prose-sm prose-invert max-w-none" — both prose-sm (banned) and max-w-none (banned) in the full word study content sheet.
Fix: Change to "prose prose-invert". Container px-6 provides margins.
Command: /impeccable polish

**[P2] Dual-mode search is undiscoverable**
Same input handles verse references, book autocomplete, AND Greek word search. Placeholder text is the only signal; first-timers type "Holy Spirit" expecting verses, get a Greek word dropdown, and don't understand what happened.
Fix: Consider explicit mode toggle pill (Verse | Word) or a first-load hint below the input.
Command: /impeccable clarify

**[P3] font-serif on verse text — potential system conflict**
Lines 1406, 1443, 1573, 1674: font-serif on scripture text. Brand reset standardized on Geist Sans only. Either document as approved exception in DESIGN.md or change to font-sans.
Command: /impeccable polish

**[P3] Mobile Sheets missing SheetTitle**
Line 1632 (word sheet) and 1653 (chapter sheet): SheetContent with no SheetTitle. The word study Sheet (line 641) has one.
Fix: Add SheetTitle with sr-only to both mobile sheets.
Command: /impeccable audit

## Persona Red Flags

**Jordan (Confused First-Timer)**: Types "Holy Spirit" in search, sees Greek word dropdown, confused. Taps a word, enters undiscovered word study mode. Can't get back to verse view. Root: dual-mode search with no mode indicator.

**Sam (Accessibility-Dependent)**: Tabs to hamburger — no name announced. Verse error fires — nothing announced. Chapter verse clicks are on <span> not <button> — keyboard-unreachable. Prev/next verse arrows have no aria-label.

**Alex (Power User)**: Arrow keys work. Save word is one click. No keyboard shortcut to open word study Sheet. Full word study buried under teaser paragraph.

## Minor Observations

- EXCERPT_COMPONENTS maps h1/h2/h3 to <p> tags — breaks markdown heading semantics for SR users
- border-l-2 border-border on blockquote (line 293) — 2px left stripe; borderline absolute ban
- key={i} on interlinear tokens (line 538) and commentary results (line 793)
- Chapter verse click uses onClick on <span> (line 1448) — keyboard-inaccessible; should be <button>
- Desktop prev/next arrows use &larr;/&rarr; text with no aria-label; SR hears "←" not "Previous verse"

## Questions to Consider

- "The dual-mode search is the most powerful feature and least explained. Would a Verse | Word toggle clarify UX or add complexity?"
- "Is font-serif on scripture text a documented DESIGN.md exception, or a brand reset gap?"
- "Chapter view replaces the verse block on desktop but is a bottom sheet on mobile. Could the desktop also be a slide-in panel?"
