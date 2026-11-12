# Design source audit

Audited 12 Nov 2026 for the Apollo-26 landing-page quality pass. Repositories are guidance or pattern sources unless a dependency is named. No third-party component code was copied into this repository.

## Used

| Source | Role in Apollo-26 | How it was applied |
| :-- | :-- | :-- |
| [google-labs-code/design.md](https://github.com/google-labs-code/design.md) | Portable design contract | Added root `DESIGN.md`: machine-readable tokens plus rationale; `.kiro/steering/design-system.md` remains normative for Kiro. |
| [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill) | Art direction | Kept one visual world, one product-first hero object, real product UI instead of a generic illustration, and browser checks at desktop/mobile sizes. |
| [pbakaus/impeccable](https://github.com/pbakaus/impeccable) | Craft and polish review | Strengthened hero hierarchy, grouped related content, themed browser surfaces, checked responsive copy, and limited motion to one authored system. Apache-2.0. |
| [Nutlope/hallmark](https://github.com/Nutlope/hallmark) | Anti-slop audit | Kept a capped container, visible primary action in the first viewport, token-only color/font use, no fabricated proof, content visible without JavaScript, and reduced-motion fallback. MIT. |
| [emilkowalski/skills](https://github.com/emilkowalski/skills) | Motion judgment | Motion has a purpose, uses transform/opacity, strong ease-out, short stagger, scoped cleanup, and no movement for reduced-motion users. MIT. |
| [greensock/gsap-skills](https://github.com/greensock/gsap-skills) | React/GSAP implementation | Added `gsap` and `@gsap/react`. `LandingMotion` scopes selectors with `useGSAP`, reverts on unmount, batches scroll writes with rAF, and keeps GSAP in a Client Component. The skills repo is MIT; the npm runtime uses the [GSAP Standard License](https://gsap.com/community/standard-license/) and this public, no-fee site is a permitted use. |
| [enesozturk/dimensional-drawing](https://github.com/enesozturk/dimensional-drawing) | Protocol anatomy | Added a proportional frame drawing derived from `FIELD_LAYOUT`: 34-byte ruler, field codes, offsets, lengths, recorded values, field schedule, and normative notes. MIT. |
| [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | Responsive/a11y checklist | Retained 44px targets, explicit status text, keyboard focus, contained horizontal scrolling, mobile one-column layout, and type measures. MIT. |
| [VoltAgent/awesome-design-md](https://github.com/VoltAgent/awesome-design-md) | DESIGN.md reference library | Used as a reference for keeping visual direction in a plain-language design artifact, not as a copied brand style. Permissive license in repository. |

## Consulted, not integrated

| Source | Decision |
| :-- | :-- |
| [DavidHDev/react-bits](https://github.com/DavidHDev/react-bits) | Visual reference only. Its animated-component approach informed the restrained orbit/progress treatment, but no component code was copied. The repository uses MIT plus Commons Clause, so vendoring would complicate Apollo-26's simple MIT distribution. |
| [magicuidesign/magicui](https://github.com/magicuidesign/magicui) | Visual reference only. A single accented instrument, rather than multiple animated effects, fit the established console direction better. MIT. |
| [nexu-io/open-design](https://github.com/nexu-io/open-design) | Not installed. Its large design workspace and skill catalogue overlap with the existing Kiro specs/steering and would add tooling without improving the shipped page. Apache-2.0. |
| [oso95/scroll-world](https://github.com/oso95/scroll-world) | Rejected for v1. It depends on generated media and a scroll-scrubbed camera world; that would add asset cost, page weight, and a visual claim unrelated to the real command path. MIT. |
| [DavidHDev/canvas-ui](https://github.com/DavidHDev/canvas-ui) | Rejected for v1. Experimental WebGL/WebGPU HTML-in-canvas effects add compatibility and performance risk. Its MIT plus Commons Clause license also complicates redistribution. |

## Review outcome

The landing page keeps the graphite mission-instrument identity but gains:

- a product-led first viewport centered on the recorded P40 run;
- a GSAP motion layer that is scoped, reversible, and optional;
- a protocol dimensional drawing generated from the normative TypeScript field layout;
- stronger information hierarchy for safety, evidence, Kiro artifacts, and local setup;
- no additional claim, metric, testimonial, or simulated telemetry.

Content from the listed sources was rephrased for compliance with licensing restrictions.
