---
target: frontend/app/library/page.tsx
total_score: 25
p0_count: 0
p1_count: 1
timestamp: 2026-06-14T22-00-44Z
slug: frontend-app-library-page-tsx
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Featured section has no skeleton during `discoverLoading`; appears abruptly after fetch |
| 2 | Match Between System and Real World | 3 | Language is clean; "Discover" mode label may not be immediately legible as a mode name |
| 3 | User Control and Freedom | 3 | Navigation trap fixed; filter has Apply/reset; minor: no Escape from search |
| 4 | Consistency and Standards | 3 | Tokens and hover states are consistent; 4 of 6 sections still use the eyebrow SectionHeader |
| 5 | Error Prevention | 2 | Silent `.catch(() => {})` in discover load; article/search errors display but have no retry |
| 6 | Recognition Rather Than Recall | 3 | Browse is self-describing; search suggestions on focus; content type labels on every card |
| 7 | Flexibility and Efficiency | 2 | No keyboard shortcuts; one rigid reading path; no history of viewed articles |
| 8 | Aesthetic and Minimalist Design | 3 | Hero and Browse are clean; 4 consecutive eyebrows in the lower half create monotony |
| 9 | Error Recovery | 2 | "Failed to load article." is a dead end — no retry button, user must re-find the item |
| 10 | Help and Documentation | 1 | No help system; subtitle is the only corpus context; search intent (keyword vs. question) ambiguous |
| **Total** | | **25/40** | **Acceptable — significant improvements since last run** |

## Anti-Patterns Verdict

**LLM Assessment**: Not AI-generated at a glance. The Browse section — three count tiles with no section label, self-describing through numbers and ArrowRight icons — reads like a real design decision. Hero hierarchy is working. The AI-tell risk that remains: the lower half runs SectionHeader on every section from Featured Authors through Pastors' Notes — four consecutive eyebrows within ~350px of page height. The rhythm is the tell.

**Deterministic scan**: Exit code 0, empty array — zero findings. All absolute-ban patterns absent.

## Overall Impression

The top third (hero + Browse) is genuinely clean. The drag is the bottom two-thirds: four sections in a row with the same 10px uppercase header. By the third occurrence the eye stops reading those headers and starts filtering them as chrome. Biggest unlock: differentiate the four section openers.

## What's Working

1. Browse panel: three count tiles, no label needed, self-describing
2. Hero hierarchy: full-width on page background, content_summary prose, hover underline affordance  
3. Navigation trap fixed: "Back to Discover" correctly resets state, contextual label via articleFromDiscover

## Priority Issues

**[P1] Four consecutive eyebrow SectionHeaders in the lower half**
- Four sections (Featured Authors, Recently Added, New Wine Archive, Pastors' Notes) all use identical 10px uppercase tracked SectionHeader within ~350px. AI-scaffold tell.
- Fix: Collapse Featured Authors label, elevate Recently Added/Pastors' Notes to text-sm font-medium headings.
- Suggested command: /impeccable layout

**[P2] Error states are dead ends**
- handleCardClick and fetchResults errors show a small red paragraph with no retry action.
- Fix: Add retry button that re-calls the failed function with the same args.
- Suggested command: /impeccable harden

**[P2] Featured section silently absent on load failure**
- fetchDocMeta failure leaves featuredDocs empty, entire hero section absent with no message.
- Fix: Add featuredError state, render minimal fallback hero.
- Suggested command: /impeccable harden

**[P2] No skeleton for Featured during discoverLoading**
- Every section except Featured has a loading placeholder. Featured appears abruptly, causing layout shift.
- Fix: Render a pulse skeleton when discoverLoading is true.
- Suggested command: /impeccable harden

**[P3] Hero year text at text-muted-foreground/50 likely fails contrast**
- Fix: Use text-muted-foreground at full opacity.
- Suggested command: /impeccable audit

## Persona Red Flags

**Jordan (First-Timer)**: Search is keyword-framed but RAG is question-optimized. "From the New Wine Archive" is jargon without known context. "Back to Discover" as back-button label is mode-name jargon.

**Casey (Mobile User)**: Featured Authors horizontal scroll has no fade affordance for off-screen pills. Content summary truncated with slice(0,180) may cut mid-word on narrow viewport. Two icon-only buttons adjacent on mobile (search + filter).

**Ruth (Project-Specific)**: `/library/authors` link may be 404. No "continue reading" behavior after returning from article. No preview signal of source type quality before clicking.

## Minor Observations

- decoration-border on hero hover underline: worth testing visibility on dark theme
- text-foreground/80 on Recently Added titles may miss 4.5:1 contrast
- last:border-b-0 on archive list items is correct
- items-baseline on archive rows produces correct visual alignment with the 01/02 index
