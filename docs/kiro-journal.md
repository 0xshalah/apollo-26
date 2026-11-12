# Kiro journal — Apollo-26

How Kiro was used to build Apollo-26, with pointers to the files that hold the evidence. Entries describe what happened; numbers come from test output, tool results, or logs named next to them.

## Kiro features in this repository

| Feature | Where | What it does here |
| :-- | :-- | :-- |
| Specs | `.kiro/specs/{acoustic-link,agc-emulator,mcp-bridge,mission-console}/` | EARS requirements → design → tasks for each subsystem. Requirement and property IDs (for example `MCP-REQ-14`, `P7`) appear in test names. |
| Steering | `.kiro/steering/` (`product`, `tech`, `structure`, `agc-safety-rules`, `design-system`) | Product claims that are allowed and banned, stack rules, module boundaries, the agent's Flight Watch safety rules S-01 to S-07, and UI tokens (`fileMatch` on `web-dashboard/**`). |
| Hooks | `.kiro/hooks/` | `flight-mode-shell-guard` (PreToolUse, blocks shell while Flight Watch is live), `pbt-on-save` (PostFileSave, fast pytest on Python edits), `test-after-spec-task` (PostTaskExec). |
| MCP | `mcp_server/`, `docs/kiro-mcp.json`, `.kiro/settings/mcp.json` | Flight Watch server: `await_telemetry_frame`, `inspect_agc_status`, `plan_dsky_sequence`, `execute_dsky_sequence`, `read_telemetry_frames`, `verify_crc16`. `execute_dsky_sequence` is never auto-approved (enforced by a test). |
| Property-based tests | `tests/` (Hypothesis P1–P8), `web-dashboard/tests/p9-frame.test.ts` (fast-check P9) | Frame codec, modem, sequence, AGC words, safety gate, and Python/TypeScript encoder equality against `contracts/vectors/frames.json`. |

## 12 Nov — plan and contracts

- Reviewed PRD v2.0 and rewrote it as v2.3: subset AGC emulator instead of running Luminary (Virtual AGC is GPL v2+), own Bell-202 modem (`fskmodem` wraps the Linux-only `minimodem`), 34-byte frame with `frame_type`, `seq`, `ref_seq`, truncated HMAC-SHA256 and CRC-16/CCITT-FALSE.
- Checked the Kiro hook docs before designing the runtime: File Create hooks fire for files the agent creates, not files written by an external daemon. The runtime trigger became a Flight Watch session that calls `await_telemetry_frame` over MCP. Decision log: `TASK.md` §5.
- Wrote steering first so later sessions inherit the safety rules and the list of banned claims.

## 12 Nov — specs and implementation

- Four specs were drafted in the requirements → design → tasks format, then implemented against them. Contracts in `contracts/` (frame format, JSON Schemas, DSKY command catalog, golden vectors) are shared by Python and TypeScript instead of duplicating constants.
- Tests found and fixed a modem edge case: a frame ending exactly at the buffer edge was not decoded until the demodulator padded `width // 8` samples.
- P9 runs the TypeScript encoder against the same golden vectors as Python (`npm run test:full`, 10,000 fast-check runs per property, run locally).

## 12 Nov — hooks firing for real

- `flight-mode-shell-guard` blocked the agent's own shell call during a live session. The MCP server had written `telemetry/FLIGHT_MODE`, the hook returned exit 2, and the agent had to stop and ask the operator to end Flight Watch before running tests. That matches steering rule S-01: tools are restricted while the command path is live.
- `pbt-on-save` runs `scripts/hooks/quick_tests.cmd` after Python saves; its latest output is in `telemetry/state/hook-pytest.txt` (not committed; runtime state).

## 12 Nov — first live Flight Watch sessions (three real bugs)

Running the agent through the real MCP server, not the test harness, found three problems the unit suite could not:

1. **Inspection window too short.** Every `plan_dsky_sequence` returned `INSPECTION_STALE` because agent tool calls were 5–30 s apart and the window was 5 s. Changed to 20 s; AGC state changes are still caught by the revision check. Catalog bumped to 1.1 so a mismatched daemon/MCP pair fails with `CATALOG_MISMATCH`.
2. **Key cadence on Windows.** Execution stopped after 1 of 29 keys with `KEY_REJECTED`. A probe showed Python 3.12 `time.monotonic` on Windows is `GetTickCount64` (15.625 ms resolution): 10 of 40 `sleep(100 ms)` calls measured 93–94 ms, below the AGC's 100 ms cadence rule. `SystemClock` now uses `perf_counter_ns` and sleeps until the deadline. Regression test: `tests/test_system_clock.py`. The safety gate halted Flight Watch as designed; nothing executed out of order.
3. **AUTH hold window too short.** A critical command must wait for a human operator's AUTH and then several agent calls; 30 s could never fit. With the operator's approval it became 120 s (catalog 1.2). Key, `ref_seq` binding, single use and sequence ordering are unchanged.

After the fixes:

- V25 N81 (seq 1): EXECUTED 29/29 keys; inspect showed R1/R2/R3 = 1250/420/3120.
- P40 critical (seq 2): HELD with reasons `NONZERO_P40_ACTIVATION` and `FRAME_CRITICAL_FLAG`; execute without AUTH refused with `AUTH_REQUIRED`; AUTH seq 3 matched; EXECUTED 36/36; P40 active with R1/R2/R3 = 1250/420/3120. 84.2 s from COMMAND accepted to execution finished, including the deliberate refused attempt (one run).

## 12 Nov — measurements and console check

- `scripts/measure_metrics.py` runs the real daemon in an isolated telemetry directory and writes `docs/metrics.json`. Loopback: 20/20 frames, median 0.59 s from upload to validated inbox record. Idle microphone listening: 3.5% of one core, 54 MB working set.
- The first over-the-air test (same laptop's speaker into its microphone array) decoded 0 of 20 frames. A probe recording showed only 0.5–1% of the captured energy near 1200 Hz and 0.1–0.2% near 2200 Hz, so the problem is the capture path, not the demodulator threshold. This is recorded as FAILED in the evidence matrix.
- The first loopback measurement accepted only 5 of 20 frames. All 20 were decoded, but each one arrived one upload late: the receiver decodes on 0.25 s hops, and the uploaded WAV had only 50 ms of trailing silence. The measurement now pads 0.3 s, as a live microphone would.
- A headless Chrome check of `/console` against a real daemon showed two gaps that were then fixed: the test panel always said UNMEASURED because the daemon never published `test.summary`, and frames accepted before the browser connected never appeared in the audit log. The daemon now publishes `docs/test-summary.json` (written from pytest's JUnit XML by `scripts/write_test_summary.py`) and backfills accepted frames on connect. Screenshot: `docs/images/console-live.png`.

## Lessons

- The agent's own latency is part of the protocol. Timing windows sized for code (5 s, 30 s) failed with an LLM in the loop; the fix was to widen windows and keep exact state checks, not to relax the checks.
- Tests with an injected `ManualClock` were correct and still missed a platform clock bug. One real-clock test now covers the boundary.
- Background terminals started by the agent do not survive between turns; the operator runs the daemon in their own terminal during live sessions.

## 12 Nov — curated design-skill pass

- Audited fourteen suggested design repositories instead of installing them all. The selected roles and licensing notes are in `docs/design-sources.md`; the visual contract now also has a portable Google-format `DESIGN.md`.
- Taste Skill and Impeccable shaped the page around one real product object: the recorded P40 run. Hallmark checks kept the first action visible, tokens centralized, content available without JavaScript, and evidence honest.
- Added `gsap` 3.15.1 and `@gsap/react` 2.1.2 (exact versions). `LandingMotion.tsx` scopes selectors and cleanup through `useGSAP`, animates only transform/opacity, and skips all motion for `prefers-reduced-motion`.
- Added `ProtocolDrawing.tsx`, a proportional 34-byte frame anatomy generated from the normative TypeScript `FIELD_LAYOUT` and the recorded COMMAND bytes. Offsets, lengths, field values and the 34-byte total are not duplicated constants.
- React Bits and Magic UI were visual references only; no component code was copied. OpenDesign, Scroll World and Canvas UI were not integrated because their tooling/media/WebGL cost did not fit the static, evidence-led page.
