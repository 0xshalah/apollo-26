# Browser demo mode: design

## Why
Judges may score from the video and a link alone. Today the full flow needs Python, a terminal, and Kiro. A `/demo` page on GitHub Pages lets anyone walk the safety story in a minute with no install.

## What the visitor does
They play the agent. The page runs the ground station, the daemon's frame validation, the MCP safety gate, and the DSKY in the browser, and the visitor clicks the agent's actions:

1. Transmit a signed P40 burn COMMAND (optionally audible as Bell-202 tones).
2. The daemon check accepts it (CRC, HMAC, sequence, range).
3. Inspect the AGC, request the canonical plan, execute. The gate refuses with `AUTH_REQUIRED`.
4. Optional abuse: execute a tampered plan (`PLAN_MISMATCH`), execute without inspecting (`INSPECTION_REQUIRED`), replay the frame (`REPLAY`), forge one with the wrong key (`HMAC`).
5. Send the operator AUTH, inspect and plan again, execute. The DSKY shows P40 and R1–R3.
6. Try the same AUTH again (`AUTH_USED`).

## Honesty rules
- The page says plainly that it is a browser simulation of the same rules, with no microphone, daemon, or Kiro agent. Nothing on it is a measurement, and it shows no performance numbers.
- No numbers are reused from `docs/metrics.json`.

## Architecture
Pure TypeScript modules under `web-dashboard/lib/demo/`, plus one client component and one static route.

| Module | Mirrors | Source of rules |
| :-- | :-- | :-- |
| `catalog.ts` | `mcp_server/planner.py` | imports `contracts/dsky-command-catalog-v1.json` directly |
| `dsky.ts` | `agc_core/agc_engine.py` key handling (VERB/NOUN/data entry, OPR ERR, KEY REL, 100 ms cadence) | engine behavior |
| `gate.ts` | `mcp_server/safety_gate.py` check order (inspection → preconditions → plan → key equality → AUTH) | catalog + gate |
| `mission.ts` | daemon acceptance, ledger, AUTH matching | `lib/frame.ts` `validateFrame` (already P9-tested) |

**Equality test, not trust.** `scripts/write_demo_vectors.py` runs the real Python planner and AGC engine over a fixed scenario list and writes `contracts/vectors/dsky-demo.json`: canonical keys, critical reasons, postconditions, and the engine state after each key sequence, including invalid sequences that must latch OPR ERR. TypeScript tests replay the same scenarios and must match exactly. A Python test fails if the committed vector file is stale.

## Time windows
The 20 s inspection window and the 120 s AUTH hold run on the real clock, as in the system. The page says so, and the next-step hint tells the visitor to inspect again or send a new COMMAND when a window closes.

## Review follow-up (25 Nov)
An independent review found gate/ledger gaps the vectors did not cover. Fixed and tested: AUTH ingest codes (`STATE`, `AUTH_USED`, `AUTH_EXPIRED`) and expiry of held commands as in `service.py`; Flight Watch HALT after a failed execution; plan refuses closed commands and DSKY preconditions; the inspection is used up after an allowed execution. Vectors now also cover the delta-v threshold boundary, PRO, CLR during data entry, the 100 ms cadence, and the OPR ERR latch.

## Out of scope
Audio decoding in the browser (the page may play tones, but validation runs on the encoded bytes), COMP ACTY blinking, plan digests, the daemon's second execution guard, and the 15-bit word representation (registers are signed integers in the ±16383 range, the same values the RPC snapshot exposes).
