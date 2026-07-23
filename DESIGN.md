# Rhemata Design System v2 — "Lumen System"
*Extracted from withlumen.app source (MIT, github.com/andrewhuang427/lumen-ai). This replaces rhemata-brand.md as the styling authority. Every component must use these tokens — no hardcoded hex values, no inline style hover handlers.*

---

## Foundation

**Stack:** shadcn/ui (new-york style), Tailwind CSS variables, lucide-react icons, `tailwindcss-animate`, `class-variance-authority` for variants.

**Theming:** Dark theme only, forced via `forcedTheme="dark"` in `next-themes` (`frontend/components/providers.tsx`) — no light theme, no toggle. All colors are HSL CSS variables consumed as `hsl(var(--token))` — never raw hex in components.

---

## Color Tokens

### `:root` (only theme) — warm charcoal
```css
--background: 60 2.7% 14.51%;
--foreground: 46.15 9.77% 73.92%;
--card: 60 2.7% 14.51%;                /* flat again — no color elevation */
--card-foreground: 48 33.33% 97.06%;
--popover: 60 2.13% 18.43%;
--popover-foreground: 60 5.45% 89.22%;
--primary: 44.05 73.83% 41.96%;        /* gold identical in both themes */
--primary-foreground: 0 0% 100%;
--secondary: 48 33.33% 97.06%;
--secondary-foreground: 60 2.13% 18.43%;
--muted: 60 3.85% 10.2%;
--muted-foreground: 51.43 8.86% 69.02%;
--accent: 48 10.64% 9.22%;             /* hover fills go DARKER than bg in dark mode */
--accent-foreground: 51.43 25.93% 94.71%;
--destructive: 0 84.24% 60.2%;
--destructive-foreground: 0 0% 100%;
--border: 60 5.08% 23.14%;
--input: 52.5 5.13% 30.59%;
--ring: 210 74.8% 49.8%;
--sidebar: 30 3.33% 11.76%;            /* sidebar darker than main */
--sidebar-foreground: 46.15 9.77% 73.92%;
--sidebar-primary: 0 0% 20.39%;
--sidebar-primary-foreground: 0 0% 98.43%;
--sidebar-accent: 60 3.45% 5.69%;
--sidebar-accent-foreground: 46.15 9.77% 73.92%;
--sidebar-border: 0 0% 92.16%;
--sidebar-ring: 0 0% 70.98%;
```

### Chart tokens
```css
--chart-1: 18.28 57.14% 43.92%;  --chart-2: 251.45 84.62% 74.51%;
--chart-3: 48 10.64% 9.22%;      --chart-4: 248.28 25.22% 22.55%;
--chart-5: 17.78 60% 44.12%;
```

---

## Typography

| Role | Font | Rule |
|---|---|---|
| UI everything | Geist Sans (`geist/font/sans`, var `--font-geist-sans`) | Default body font via Tailwind `fontFamily.sans` |
| Scripture / reading text | System serif stack: `ui-serif, Georgia, Cambria, "Times New Roman", Times, serif` | Applied via `font-serif` on reading containers only |
| Mono | `ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas` | Strong's numbers, code |

**Rules:**
- NO Lora, NO Inter, NO Google Fonts imports. Geist + system serif only.
- Reading headings: `text-xl font-medium tracking-wide` — never bold, never larger than xl inside readers.
- **Exception:** Study Mode's verse-as-focal-point display (`app/study/page.tsx`) is exempt from this size cap — it renders at `text-xl md:text-2xl` so the verse itself reads as the screen's visual focal point. This is a deliberate, single-purpose exception, not general permission to exceed `xl` elsewhere.
- UI text default `text-sm`; metadata `text-sm text-muted-foreground` or `text-xs`.
- Letter-spacing normal; the only tracking used is `tracking-wide` on serif headings.

---

## Shape, Depth, Spacing

```css
--radius: 0.75rem;   /* lg */
/* md = calc(var(--radius) - 2px), sm = calc(var(--radius) - 4px) */
```
- Buttons/inputs: `rounded-md`. Cards/popovers: `rounded-lg` (via shadcn card). Pills/badges: `rounded-md` or `rounded-full` for tags only.
- Shadows are whisper-subtle and layered — always `0 1px 3px hsl(0 0% 0% / 0.1)` base plus one offset layer. Buttons get `shadow` / `shadow-sm`. Cards on same-color backgrounds rely on `border` not shadow.
- **Depth philosophy: flat.** Card bg == page bg in both themes. Separation comes from 1px borders and spacing, not fills or shadows. Popovers/sheets are the only lifted surfaces.
- Spacing rhythm: `gap-2` tight, `gap-4` standard. Reader content: `max-w-2xl` centered, `px-4 pt-4 pb-12 md:pt-8 md:pb-24`.
- Scroll containers get a sticky top fade: `pointer-events-none sticky top-0 z-10 h-8 bg-gradient-to-b from-background to-transparent`.

---

## Component Recipes (shadcn new-york)

**Button** (cva variants, copy verbatim):
- Base: `inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4`
- default: `bg-primary text-primary-foreground shadow hover:bg-primary/90`
- outline: `border border-input bg-background shadow-sm hover:bg-accent hover:text-accent-foreground`
- secondary: `bg-secondary text-secondary-foreground shadow-sm hover:bg-secondary/80`
- ghost: `hover:bg-accent hover:text-accent-foreground`
- link: `text-primary underline-offset-4 hover:underline`
- Sizes: default `h-9 px-4 py-2`, sm `h-8 px-3 text-xs`, lg `h-10 px-8`, icon `h-9 w-9`

**Hover states:** ALWAYS `hover:bg-accent` Tailwind classes. NEVER JavaScript onMouseEnter/onMouseLeave handlers. NEVER inline styles.

**Icons:** lucide-react, sized `size-4` (16px) inside buttons, `h-4 w-4` standalone. Loading: `<Loader2 className="h-4 w-4 animate-spin" />`.

**Focus:** `focus-visible:ring-1 focus-visible:ring-ring` (the blue ring) everywhere.

---

## Rhemata Extension Rules (surfaces Lumen doesn't have)

| Rhemata element | Token mapping |
|---|---|
| Inline citations | `text-primary underline-offset-4 hover:underline` (link variant) — drop the old #d4b96a highlight-pill treatment |
| Citation source panel | Sheet component (shadcn), `bg-popover` |
| Topic tag pills | Badge component: `bg-secondary text-secondary-foreground rounded-md text-xs` — no gold tinted backgrounds |
| Search `<mark>` highlights | `text-primary font-semibold bg-transparent` |
| Verse numbers (sup) | `text-xs text-muted-foreground` |
| Active verse highlight | `bg-accent` |
| Interlinear word blocks | `rounded-md border hover:bg-accent` with Tailwind, mono for Strong's |
| Study tabs | shadcn Tabs component, default styling |
| Library book cards | `border rounded-lg hover:bg-accent transition-colors` — flat, no shadow |
| Sidebar | shadcn Sidebar primitives with the `--sidebar-*` tokens |
| Gold "New Chat" CTA | Button default variant (keeps gold via --primary) |

## Migration Bans
1. No hardcoded hex anywhere (`#1f1e1d`, `#262624`, `#d4b96a`, `#b49238` all dead — search and destroy)
2. No `onMouseEnter`/`onMouseLeave` hover handlers — Tailwind hover: classes only
3. No inline `style={{}}` for spacing/color (interlinear blocks must be rebuilt with Tailwind)
4. No Lora/Inter imports, no logo gradient
5. No new shadows, radii, or colors outside this file
