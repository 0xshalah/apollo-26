---
name: Apollo-26 Mission Instruments
version: 1.1
source: docs/archive/mockups/dashboard-page.html
surfaces:
  - landing
  - ground-station
  - mission-console
modes:
  landing: persuade
  ground-station: operate
  mission-console: operate
fonts:
  ui: Host Grotesk
  telemetry: Atkinson Hyperlegible Mono
colors:
  paper: "oklch(13.5% 0.009 250)"
  paper-2: "oklch(17.5% 0.010 250)"
  paper-3: "oklch(10.5% 0.008 250)"
  ink: "oklch(96% 0.005 250)"
  ink-2: "oklch(84% 0.008 250)"
  muted: "oklch(69% 0.011 250)"
  rule: "oklch(26.5% 0.011 250)"
  rule-2: "oklch(39% 0.013 250)"
  accent: "oklch(83% 0.155 80)"
  cool: "oklch(78% 0.125 245)"
  ok: "oklch(78% 0.155 150)"
  bad: "oklch(70% 0.17 25)"
radii:
  card: 8px
  control: 6px
  tag: 4px
---

# Apollo-26 visual identity

Apollo-26 looks like a precision instrument assembled from three eras: Bell-202 communications, Apollo DSKY hardware, and a modern agent control surface. It uses graphite surfaces, white type, amber actions, blue technical references, green verified/live state, and red refusal/failure state. The interface is dense but calm. Lines, tables, measured values, and operational state provide the visual interest.

The normative Kiro rules live in [`.kiro/steering/design-system.md`](.kiro/steering/design-system.md). This file is its portable `DESIGN.md` representation for tools that support the [Google Labs format](https://github.com/google-labs-code/design.md). When either file changes, update the other in the same commit.

## Landing page

Mode: **Persuade**, grounded in real product evidence.

The first viewport has one memorable object: the recorded P40 mission card. It shows the real COMMAND bytes, mini-DSKY postcondition, safety-gate refusal, and key-execution result from `docs/metrics.json`. The headline and two actions sit beside it. A static orbit/grid field creates depth; it does not imply telemetry.

Below the fold, the story is ordered by the visitor's questions:

1. What is the command path?
2. What stops the model from acting freely?
3. What happened in the real run?
4. What is measured and what failed?
5. Where is the Kiro evidence?
6. How can I run it?

Motion is progressive enhancement: a short hero entrance, one reveal for the protocol anatomy sheet, a two-pixel scroll-progress line, and slight parallax on decorative orbit lines. GSAP is scoped to the landing root and disabled for reduced-motion users. Content remains visible without JavaScript.

## Ground station

Mode: **Operate**. Keep the form compact and explicit. The operator chooses one supported v1 command, enters monotonically increasing sequence values and session-only keys, signs, reviews the exact frame bytes, then transmits. Playback completion never implies daemon acceptance.

## Mission console

Mode: **Operate**. Prioritize scanability: navigation rail; sticky command header with frame window, latest sequence, AGC display and Flight Watch; KPI ribbon; real spectrum or an explicit unmeasured frequency reference; latest-link snapshot with validation gates; filterable audit ledger; system, test and diagnostic panels; pinned read-only DSKY. COMMAND fields never substitute for AGC state. Missing facts show `AWAITING`, `UNMEASURED`, or `—`; stale data stays visible with a `STALE` label.

## Material and behavior

- Card borders: one-pixel `rule-2`; internal separators: one-pixel `rule`.
- Host Grotesk carries UI and headings; Atkinson Hyperlegible Mono is reserved for bytes, code, timestamps, identifiers, and measured values.
- Every interactive target is at least 44px high and has an immediate amber focus ring.
- Status always combines text and color.
- Never reproduce mockup placeholders, sample metrics, fake charts, fake testimonials, or out-of-scope commands.
- Never claim the whole laptop is offline. The local command path binds to loopback; Kiro uses a cloud model.
- Over-the-air decoding is currently failed/unverified and remains visible as such.
