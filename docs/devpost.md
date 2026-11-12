# Devpost draft — Apollo-26

Category: **Frankenstein**. Every number below links back to `docs/metrics.json`, `docs/pbt-report.md`, or the live-session log in `TASK.md`. Update this file if those change.

## Tagline

An authenticated sound-only command link from a 2026 web ground station to a 1969-style DSKY, flown by a Kiro agent through a code-enforced MCP safety gate.

## Inspiration

Apollo crews typed VERB/NOUN pairs into a DSKY. Old modems pushed bytes through phone lines as audio. Today's agents can type for us. Apollo-26 stitches those three eras together and asks one question: how do you let an LLM agent press buttons on a critical machine without trusting the LLM?

## What it does

1. The ground station page (`/ground`, Next.js static export) signs a 34-byte frame (sequence number, truncated HMAC-SHA256, CRC-16/CCITT-FALSE) and plays it as Bell-202 FSK at 300 baud.
2. A Python daemon receives the audio (microphone, WAV file, or loopback), demodulates it with its own NumPy modem, and validates sync → CRC → HMAC → replay → ranges. Rejected frames are logged and never reach the agent.
3. A Kiro agent runs a **Flight Watch** session over MCP: `await_telemetry_frame` → `inspect_agc_status` → `plan_dsky_sequence` → `execute_dsky_sequence`.
4. Execution passes a safety gate written in code, not in the prompt (`mcp_server/safety_gate.py`), plus an independent guard in the daemon. The agent can only send the canonical key sequence for that frame. Critical commands (P40 burn, V37/V34 during P40) also need a separate operator AUTH frame, bound to the command's sequence number and single-use.
5. An AGC-faithful subset emulator (15-bit ones' complement words, DSKY state machine, P00/P40, V25/V34/V37) presses the keys at ≥100 ms cadence. The mission console (`/console`) shows its real state over a local WebSocket.

## How we built it with Kiro

- **Specs** for four subsystems (`.kiro/specs/`): EARS requirements → design → tasks. Requirement and property IDs appear in test names.
- **Steering** (`.kiro/steering/`) carries the allowed and banned claims, module boundaries, the agent's Flight Watch rules S-01 to S-07, and the design tokens.
- **Hooks** (`.kiro/hooks/`): a PreToolUse guard that blocks the agent's shell while Flight Watch is live (it really blocked the agent during development), fast property tests on Python save, and tests after spec tasks.
- **MCP**: a six-tool Flight Watch server. `execute_dsky_sequence` is never auto-approved, and a test enforces that.
- **Property-based testing**: Hypothesis P1–P8 and fast-check P9. Full-profile run: 132 tests passed; 10,000 examples each for the frame, safety-gate and AGC-word properties and the stateful AGC machine; 300–1,000 for the audio-heavy modem properties (`docs/pbt-report.md`).

## Challenges

Running the agent live against the real MCP server found three bugs that the unit tests did not:

- Every plan came back `INSPECTION_STALE`: agent tool calls were 5–30 s apart and the inspection window was 5 s. We widened it to 20 s and kept the exact AGC state-revision check.
- Execution stopped at key 2 of 29. On Windows with Python 3.12, `time.monotonic` has 15.625 ms resolution, so 10 of 40 measured 100 ms sleeps were 93–94 ms, under the AGC's cadence rule. The fix is a high-resolution clock plus a real-clock regression test. The gate halted safely; nothing ran out of order.
- The AUTH hold window (30 s) could never fit a human operator plus several agent calls. It is now 120 s; key, binding, single use, and ordering are unchanged.

The acoustic channel is the open problem. Our first over-the-air test (the same laptop's speaker into its own microphone array) decoded **0 of 20** frames; the microphone captured almost no energy at 1200/2200 Hz. Phone-to-laptop testing is next.

## Accomplishments

- Live Kiro run of a critical P40 command: held without AUTH, refused with `AUTH_REQUIRED`, then executed 36/36 keys after the operator AUTH arrived, with R1/R2/R3 = 1250/420/3120 on the DSKY.
- Loopback path: 20/20 frames accepted, median 0.59 s from upload to validated inbox record.
- Daemon idle while listening: 3.5% of one core, about 54 MB working set.

## What we learned

The agent's latency is part of the protocol. Windows sized for code broke as soon as an LLM was in the loop. The answer was to widen time windows and keep exact state checks, never to relax the checks.

## What's next

- Phone → laptop decode trial at 0.5 m (target ≥95% of 20 frames).
- Bring the agent path toward the 10 s target (one live run took 84 s, including a deliberate refused attempt).
- Optional adapter to the real yaAGC as a separate process.

## Honest limits

The command path (daemon, MCP server, emulator) binds only to 127.0.0.1, but the Kiro agent uses a cloud LLM. The acoustic channel can be overheard and jammed; HMAC prevents forgery, not eavesdropping. The emulator is a subset, not Apollo flight software.

## Built with

Python 3.12, NumPy, sounddevice, aiohttp, jsonschema, MCP Python SDK, Hypothesis, pytest, Next.js (static export), TypeScript, Tailwind CSS, Web Audio, Web Crypto, fast-check, Kiro (specs, steering, hooks, MCP).

## Links

- Repository: https://github.com/0xshalah/apollo-26
- Ground station (GitHub Pages): https://0xshalah.github.io/apollo-26/ground/
- Video: _add the public YouTube link_
