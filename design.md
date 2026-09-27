# Design system — Vercel

> Visual reference: Vercel home / AI Gateway / Customers / Pricing.
> Implementation: `apps/web/app/globals.css` (token variables + class chrome).
> Class names in components stay unchanged — only the `:root` token values and a small set of foundational styles get rewritten.

## Principles

- Near-white canvas (`#fafafa`) carrying near-black ink (`#171717`). Near-zero chromatic chrome.
- The mesh gradient (cyan → blue → violet → magenta → amber) is the entire decorative system, confined to the hero.
- Two button shapes by context: black pill (`100px`) for marketing CTAs, 6px square for nav/app controls.
- Geist Sans for tightly-tracked display type, Geist Mono for uppercase technical eyebrows.
- Hairline (`#ebebeb`) borders + whisper shadow, never heavy elevation.

## Colors

### Surface
- `--bg` `canvas` `#fafafa`
- `--surface` `canvas-elevated` `#ffffff`
- `--surface-2` `hairline-soft` `#f2f2f2`

### Text
- `--text` `ink` `#171717`
- `--muted` `body` `#4d4d4d`
- `--faint` `faint` `#a1a1a1`

### Borders / signals
- `--line` `hairline` `#ebebeb`
- `--accent` `link` `#0070f3` (links, focus, positive signal)
- `--accent-deep` `link-deep` `#0761d1`
- `--accent-soft` `link-soft` `#d3e5ff`
- `--danger` `error` `#ee0000`

### Brand gradient stops (hero only)
- develop: `#007cf0` → `#00dfd8`
- preview: `#7928ca` → `#ff0080`
- ship: `#ff4d4d` → `#f9cb28`

## Typography

| Token | Size | Weight | Letter-spacing |
|---|---|---|---|
| display-xl | 48 | 600 | -2.4px |
| heading-lg | 32 | 600 | -1.28px |
| heading-md | 20 | 600 | -0.4px |
| label-sm | 14 | 500 | -0.28px |
| mono-eyebrow | 12 | 500 | 0 (uppercase Geist Mono) |
| body-lg | 16 | 400 | 0 |
| body-md | 14 | 400 | 0 |
| body-sm | 12 | 400 | 0 |
| button-lg | 16 | 500 | 0 |
| button-md | 14 | 500 | 0 |

Fonts: **Geist Sans** (display + body), **Geist Mono** (code + eyebrows). Fallback: Inter / JetBrains Mono → system Arial.

## Spacing

4 → 8 → 12 → 16 → 24 → 32 → 40 → 64 → 96 → 128 (base 4px).
Card interiors `24–32`, section bands `96–128`, button padding horizontal-only (pill `0 14`, square `0 6`).

## Radii

| Token | Value | Use |
|---|---|---|
| sm | 6px | nav/app buttons, inputs |
| md | 12px | feature cards, code blocks |
| lg | 16px | pricing cards |
| pill | 100px | marketing CTAs |
| full | 9999px | icon buttons, avatars |

## Buttons

- `.button-primary` — black pill (`var(--accent)` → `var(--text)` ink), 100px radius, `padding: 0 14px`.
- `.button-secondary` — white pill, ink text, 1px hairline, 100px radius.
- `.button-quiet` — 6px square, transparent, 1px hairline.
- `.button` base shape (8px square) → remap to Vercel shapes: `.button-primary` pill, `.button-quiet` square.

## Hero

- White canvas, full-width.
- Mesh gradient bloom (cyan / blue / violet / magenta / amber at low alpha) behind headline — the page's only color.
- Display heading `clamp(52px, 8vw, 106px)`, weight 600, tracking -0.085em.

## Cards

- White (`var(--surface)`), 1px hairline, 12px radius, 24px padding. No heavy shadow.
- Whisper shadow `0 1px 1px rgba(0,0,0,.04)` only when lifted.

## Do / Don't

- Keep canvas near-white, ink near-black; reserve color for hero + small accents.
- Don't fill large surfaces with violet/cyan/pink/blue.
- Don't mix pill and square buttons within one context.
- Don't set body copy in pure black — use `#171717`.
- Don't loosen display tracking on large headings.
