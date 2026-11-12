---
inclusion: fileMatch
fileMatchPattern: ["web-dashboard/**/*.ts","web-dashboard/**/*.tsx","web-dashboard/**/*.css"]
---

# Apollo-26 Design System

Source: the archived dashboard mockup `docs/archive/mockups/dashboard-page.html` ("Console" theme: graphite, grotesk sans, amber accent). The operator chose it over the earlier PRD §8 style on 12 Nov 2026. Its visual language is adopted in full; its sample numbers, keypad, and out-of-scope verbs are not. Tokens live in `web-dashboard/app/globals.css` (`@theme`). This file is the rule source; the CSS is the implementation.

## Color tokens

| Token | Value | Tailwind | Role |
| :-- | :-- | :-- | :-- |
| Paper | `oklch(13.5% 0.009 250)` | `paper` | Page background, KPI cells, DSKY digit cells |
| Paper 2 | `oklch(17.5% 0.010 250)` | `paper-2` | Panel/card surface, hover |
| Paper 3 | `oklch(10.5% 0.008 250)` | `paper-3` | Sidebar, top bars, inputs, table header, wells |
| Ink / Ink 2 | `oklch(96% …)` / `oklch(84% …)` | `ink`, `ink-2` | Primary / secondary text |
| Muted | `oklch(69% 0.011 250)` | `muted` | Labels, notes, placeholders |
| Rule / Rule 2 | `oklch(26.5% …)` / `oklch(39% …)` | `rule`, `rule-2` | Hairlines / card and control borders |
| Accent (amber) | `oklch(83% 0.155 80)` | `accent`, `accent-ink`, `accent-soft` | Primary action, selected control, focus ring, warnings |
| Cool (blue) | `oklch(78% 0.125 245)` | `cool`, `cool-soft` | Info, selected row, raw bytes/hex, spectrum bars, lit COMP/UPLINK lamps |
| OK (green) | `oklch(78% 0.155 150)` | `ok`, `ok-soft` | Accepted/PASS/LIVE, DSKY digits, field bytes |
| Bad (red) | `oklch(70% 0.17 25)` | `bad`, `bad-soft` | Rejected/FAIL/DISCONNECTED, lit KEY REL/OPR ERR lamps |

Rules:
- `--color-*: initial` removes the Tailwind default palette. Use only these tokens; no raw hex or extra colors in components.
- Status is always text plus color (`Accepted`, `Rejected`, `PASS`, `FAIL`, `STALE`). Color is never the only cue.
- Green means a measured or live value from the system; amber means "act here" or "attention". Do not use either as decoration.

## Typography

| Role | Family | Tailwind | Use |
| :-- | :-- | :-- | :-- |
| UI and headings | Host Grotesk 400/500 | `font-sans` (body default) | Everything that is not telemetry. Headings weight 500, tracking −0.025em. |
| Telemetry | Atkinson Hyperlegible Mono 400/500 | `font-mono` + `tabular` | Bytes, hex, bits, seq, event ids, timestamps, DSKY digits, measured values |

- Fonts load through `next/font/google` (downloaded at build time, served from `out/`). No runtime font or CDN request.
- Sentence-case labels in `text-xs` medium `muted`; no letter-spaced uppercase labels.
- Sizes follow the mockup scale: 0.75 / 0.84 / 0.94 / 1.125 / 1.35 / 1.65 rem.

## Shape

- Radius: `rounded-card` 8px (panels, ledger card, DSKY bezel, home cards), `rounded-pill` 6px (buttons, inputs, segmented controls, wells), `rounded-tag` 4px (pills, nav keys).
- Borders: 1px `rule-2` on cards and controls, `rule` for internal hairlines. Cell grids use `gap-px` over `bg-rule`.
- No drop shadows except inset accents (3px amber left bar on the current nav item, 2px cool bar on a selected row, 2px amber underline on a pressed segment). Backdrop blur only behind the DSKY sheet.

## Components

- Shared classes in `globals.css`: `.btn`, `.btn-amber` (primary), `.input`, `.seg-group` (segmented control; `aria-pressed` or a checked radio marks the active segment).
- `Panel`: `rounded-card` `paper-2` card, title row with a `rule` hairline, `p-4` body.
- `Chip`: tinted pill. Tones `ok`, `warn` (amber), `bad`, `info` (cool), `muted`.
- `AppShell`: mockup sidebar on `paper-3` with brand mark, route links (TX/RX keys), numbered "On this page" links, and a "Daemon link" status card at the bottom.
- KPI ribbon: four `paper` cells separated by `rule` hairlines, mono values, muted notes.
- Audit ledger card: title row with verdict `.seg-group`, toolbar row with search, table with `paper-3` header and sticky `EVT-n` first column.
- DSKY dock: `paper-3` column, bezel with PROG/VERB/NOUN and R1–R3 in green mono, lamps as bordered pills with `ON`/`OFF` text. Read-only; no keypad.

## Data honesty (unchanged from product rules)

- Every dynamic value comes from the encoded frame (`/ground`) or a schema-valid WebSocket event (`/console`).
- Before data arrives: `AWAITING`, `UNMEASURED`, or `—`. After disconnect: retained values marked `STALE`, plus a `DISCONNECTED` banner.
- No placeholder numbers, sample rows, timers that animate data, random values, or generated waveforms. The mockup's sample values (for example SNR, latency, coverage figures) are not reproduced.
- Never render the banned claims listed in `product.md` (for example V97/V06/V16, 1200 baud, "100%", "0 dB", Luminary/Colossus as running software).

## Interaction and accessibility

- Focus: 2px amber outline, 2px offset, via `:focus-visible`.
- Touch targets stay at 44px (`min-h-11` / `.btn` / `.input`), slightly taller than the mockup's 36px controls.
- Skip link to `#main`; one `h1` per route; native labels, `aria-describedby` for hints and errors; `role="status"` (polite) for connection and transmission state; `role="alert"` only for disconnection.
- `prefers-reduced-motion: reduce` disables transitions and smooth scroll globally. Do not add animation that carries meaning.
- Layout: every route uses `AppShell` (15.25rem rail from `lg`; compact top bar below). `/console`: sticky two-row command header (title/freshness, then frame window/latest seq/AGC/Flight Watch); KPI ribbon; spectrum or truthful reference-frequency ruler + latest-link snapshot; audit ledger + system state; test evidence + diagnostics. DSKY is a right dock from `xl` (80rem) and a `<dialog>` sheet with a sticky quick bar below. `/ground`: top bar, compose + keys left, transmit + preview right from `lg`. Must work at 375px with no page-level horizontal scroll.
- Landing motion is progressive enhancement in `components/landing/LandingMotion.tsx`: GSAP + `@gsap/react`, selectors scoped to the landing root, cleanup through `useGSAP`, hero entrance, one protocol-sheet reveal, 2px scroll progress, and slight orbit parallax. Only transform/opacity change; `prefers-reduced-motion` skips the system; content is visible without JavaScript.
- Landing (`/`): follows `docs/archive/mockups/landing-page.html` but uses a tighter mission-briefing composition: floating nav; viewport-height grid/orbit hero; live P40 card with packet bytes, mini-DSKY, safety-gate timeline and recorded outcomes; numbered pipeline; five-stage gate; prompt-vs-code comparison; live-run findings; evidence cards/table; Kiro cards; quick start; FAQ; closing CTA. Every figure comes from `docs/metrics.json` or `docs/test-summary.json` via `lib/landing-data.ts` at build time; the mockup's animated cloud, simulated waveform, toggleable demo, and claims ("0 socket", "24 dB", "bebas exploit") are not used.
- English is the only UI language in v1.
