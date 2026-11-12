---
inclusion: fileMatch
fileMatchPattern: ["web-dashboard/**/*.ts","web-dashboard/**/*.tsx","web-dashboard/**/*.css"]
---

# Apollo-26 Design System

Concept: Celestial Brutalism and Swiss Aerospace Luxury (PRD §8). The UI is an instrument panel: dark, flat, hairline-ruled, dense with real data, and quiet when there is no data. Tokens live in `web-dashboard/app/globals.css` (`@theme`). This file is the rule source; the CSS is the implementation.

## Color tokens

| Token | Value | Tailwind | Role |
| :-- | :-- | :-- | :-- |
| Cosmic Void | `#050608` | `void` | Page background, deepest wells, text on electrum fills |
| Lunar Titanium 900 | `#0a0d12` | `lunar-900` | Primary panel surface |
| Lunar Titanium 800 | `#0f141c` | `lunar-800` | Raised or selected surface, inputs, table header |
| Apollo Electrum Gold | `#e6c875` | `electrum` | Text, focus ring, primary action, warnings (as filled chip) |
| DSKY Phosphor | `#00ff88` | `phosphor` | DSKY digits, bytes, live/accepted state, spectrum bars |

Rules:
- These five values are the entire palette. Every other tone is one of them at reduced opacity (`electrum/70` muted text, `electrum/15` hairlines). Do not add hex values, Tailwind default palette colors, or gradients.
- Muted text must stay at `electrum/60` or higher on `void`/`lunar-*` to keep WCAG AA contrast.
- Phosphor means "a measured or live value from the system". Do not use it for decoration, headings, or buttons.
- Warning/failed/rejected states use a filled electrum chip with void text plus an explicit word (`REJECTED`, `FAILED`, `STALE`). Color is never the only cue.

## Typography

| Role | Family | Tailwind | Use |
| :-- | :-- | :-- | :-- |
| Display | Italiana | `font-display` | Route `h1`, panel-group titles, DSKY sheet title. Large sizes only (≥ 1.5rem). |
| UI | Syne | `font-ui` (body default) | Labels, navigation, buttons, table headers, prose |
| Telemetry | Space Mono | `font-mono` + `tabular` | Bytes, hex, bits, seq numbers, timestamps, DSKY digits, measured values |

- Fonts load through `next/font/google`, which downloads them at build time and serves them from `out/`. No runtime font or CDN request.
- Labels: uppercase Syne, `text-xs`, letter-spacing `0.14em`–`0.18em`.
- Numbers that can change use `font-mono tabular` (tabular numerals, slashed zero) so columns do not shift.

## Shape and rules

- Hairlines: 1px borders in `electrum/10`–`electrum/25`. Grids of cells use `gap-px` over an `electrum/10`–`electrum/15` background.
- No border radius, shadows, blur, or glassmorphism.
- Corner ticks (`.ticks`) frame primary instruments only: the ground frame preview, the console spectrum, the selected-frame inspector, and the DSKY bezel. Never on ordinary panels.
- Panels use the `Panel` component: hairline box, uppercase title bar, `p-4` body.

## Components

- `Chip`: text-labelled state. Tones: `ok` (phosphor outline), `warn` (electrum fill), `info` (electrum outline), `muted`.
- DSKY: PROG/VERB/NOUN two-digit cells, R1–R3 as `+00000`, four lamps (`COMP ACTY`, `UPLINK ACTY`, `KEY REL`, `OPR ERR`) with `ON`/`OFF` text. Read-only on `/console`; no keypad.
- Audit table: sticky first column with the row-select button, horizontal scroll confined to the labelled table region, `N/A` for null gates, `UNMEASURED` for missing SNR.

## Data honesty

- Every dynamic value comes from the encoded frame (`/ground`) or a schema-valid WebSocket event (`/console`).
- Before data arrives: `AWAITING`, `UNMEASURED`, or `—`. After disconnect: retained values marked `STALE`, plus a `DISCONNECTED` banner.
- No placeholder numbers, sample rows, timers that animate data, random values, or generated waveforms.
- Never render the banned claims listed in `product.md` (for example V97/V06/V16, 1200 baud, "100%", "0 dB", Luminary/Colossus as running software).

## Interaction and accessibility

- Focus: 2px electrum outline, 2px offset, via `:focus-visible`.
- Touch targets: `min-h-11` (44px) on every button, link, input, and select.
- Skip link to `#main`; one `h1` per route; native labels, `aria-describedby` for hints and errors; `role="status"` (polite) for connection and transmission state; `role="alert"` only for disconnection.
- `prefers-reduced-motion: reduce` disables transitions and smooth scroll globally. Do not add animation that carries meaning.
- Layout: single column below `lg` on `/ground`; on `/console` the DSKY is a pinned right dock at `xl` (80rem) and above, and a native `<dialog>` sheet with a sticky quick bar below that. Must work at 375px with no page-level horizontal scroll.
- English is the only UI language in v1.
