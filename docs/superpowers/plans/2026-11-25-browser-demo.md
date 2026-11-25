# Browser demo mode implementation plan

> For agentic workers: use superpowers:executing-plans; steps use checkbox syntax.

**Goal:** a static `/demo` route where a visitor plays the agent against TypeScript ports of the planner, safety gate, and DSKY.
**Architecture:** pure modules in `web-dashboard/lib/demo/`, verified against Python-generated vectors; one client component.
**Tech stack:** TypeScript, Vitest, Next.js static export; Python for vectors.
**Spec:** `docs/superpowers/specs/2026-11-25-browser-demo-design.md`

## Global constraints
- Rules come from `contracts/dsky-command-catalog-v1.json`; no duplicated constants without an equality test.
- No measured numbers on the page; label it a simulation.
- Design tokens from `.kiro/steering/design-system.md` only; 44 px targets; works at 375 px.

## Task 1: golden vectors from Python
- [x] Write `scripts/write_demo_vectors.py` (planner + `AgcEngine` over fixed scenarios) → `contracts/vectors/dsky-demo.json`.
- [x] Add `tests/test_demo_vectors.py`: regenerating in memory equals the committed file.
- [x] Run both.

## Task 2: catalog planner + DSKY (TDD)
- [x] Write `web-dashboard/tests/demo-vectors.test.ts` that replays every scenario through `planCommand` and `Dsky`. Run it: must fail (modules missing).
- [x] Implement `lib/demo/catalog.ts` and `lib/demo/dsky.ts`. Run: pass.

## Task 3: safety gate + mission (TDD)
- [x] Write `web-dashboard/tests/demo-mission.test.ts`: P40 without AUTH → `AUTH_REQUIRED`; tampered keys → `PLAN_MISMATCH`; no inspection → `INSPECTION_REQUIRED`; state change after inspection → `INSPECTION_STALE`; replay → `REPLAY`; forged → `HMAC`; AUTH then execute → postcondition matched; AUTH reuse → `AUTH_USED`; non-critical V25 executes without AUTH. Run: fail.
- [x] Implement `lib/demo/gate.ts` and `lib/demo/mission.ts`. Run: pass.

## Task 4: UI and route
- [x] `components/demo/DemoClient.tsx`, `app/demo/page.tsx`, add `demo` to `AppShell` routes, landing link.
- [x] lint, typecheck, test, build, verify:export; screenshot desktop + 390 px; impeccable detector.

## Task 5: review and docs
- [x] Independent code review (semantic_reviewer) of the diff; fix Critical/Important findings.
- [x] README, devpost, video script, evidence matrix mention `/demo`.
