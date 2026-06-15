---
target: frontend/app/library/page.tsx
total_score: 24
p0_count: 0
p1_count: 2
timestamp: 2026-06-14T21-47-01Z
slug: frontend-app-library-page-tsx
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Skeleton loaders + article spinner present; no global in-flight indicator when navigating from Discover to article |
| 2 | Match System / Real World | 3 | Labels are natural; "From the New Wine Archive" assumes users know what New Wine is |
| 3 | User Control and Freedom | 2 | "Back to results" in article reader goes to empty search mode, not back to Discover — dead end from featured section |
| 4 | Consistency and Standards | 3 | Cohesive vocabulary; minor: New Wine list items gain rounded on hover while cards always have it |
| 5 | Error Prevention | 3 | Delete confirmation present; article errors caught |
| 6 | Recognition Rather Than Recall | 3 | Browse tiles show counts; source kinds labeled; authors have images |
| 7 | Flexibility and Efficiency | 2 | No keyboard navigation; no next/prev in article reader |
| 8 | Aesthetic and Minimalist Design | 2 | SectionHeader eyebrow on all 6 sections — absolute-ban pattern |
| 9 | Error Recovery | 2 | Errors shown with no retry affordance or actionable copy |
| 10 | Help and Documentation | 1 | Zero onboarding — new users have no idea what this corpus is |
| **Total** | | **24/40** | **Acceptable** |

## Anti-Patterns Verdict

Hierarchy principle (no card → card → flat list) is well-executed. SectionHeader with identical small-caps eyebrow appears on all 6 sections — this is the absolute-ban "eyebrow on every section" pattern. Deterministic scan: clean (exit 0).

## Overall Impression

Strong structural thinking, undermined by eyebrow proliferation and a UX trap in the article reader back-navigation.

## Priority Issues

**[P1] Eyebrow on every section** — SectionHeader appears on all 6 sections (Featured, Browse, Featured Authors, Recently Added, New Wine Archive, Pastors' Notes). Remove from Featured and Browse; keep on 3 where orientation genuinely helps. Fix: /impeccable layout.

**[P1] "Back to results" dead end** — Article opened from Discover mode returns to empty search state, not Discover. Track origin and show "← Back to Discover" vs "← Back to results" accordingly. Fix: /impeccable harden.

**[P2] Hero has no click affordance** — No visual signal that the hero content is interactive; cursor:pointer only on hover, invisible on touch. Add "Open →" text or hover:underline on title. Fix: /impeccable polish.

**[P2] No context for new users** — "Discover" + search box gives no indication of what corpus/tradition this is. Add a subtitle under the H2: "Search sermons, articles, and books from the charismatic tradition." Fix: /impeccable clarify.

**[P2] Hero grid breaks on mobile** — grid-cols-[1fr_200px] has no mobile breakpoint; 390px screens get ~140px left column. Recently Added grid-cols-3 produces ~120px cards. Fix: /impeccable adapt.

## Persona Red Flags

**Jordan (First-Timer):** No corpus explanation, "New Wine Archive" is opaque, "Pastors' Notes" has no explanation of whose notes. Back-to-results trap on article reader exit.

**Casey (Mobile):** Hero grid two-column at 390px is cramped. Recently Added grid-cols-3 at mobile produces unusable ~120px cards.

**Daniel (Charismatic Lay Believer):** Source curation (the differentiator) is invisible on landing. Trust signal missing — nothing identifies the tradition until you recognize a teacher name.

## Minor Observations

- "See all →" in Recently Added calls handleBrowseTile("all") — shows all content, not recently-added filtered. Label should be "Browse all →".
- The logo gradient bar in decorative panel is the only appearance of this brand gradient in the UI — orphaned styling decision.
- Error messages have no retry buttons.
- source_name filtering uses .toLowerCase().includes("new wine") — fragile.
