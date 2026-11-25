# Devpost draft: Apollo-26

Category: **Frankenstein**. Every number below comes from `docs/metrics.json`, `docs/pbt-report.md`, `docs/evidence-matrix.md`, or the live-session log in `TASK.md`. Update this file if those change.

## Tagline

Agent safety for physical systems: a Kiro agent flies a 1969 Apollo guidance computer over a sound-only link, and code, not the prompt, decides which buttons it may press.

## The problem

AI agents are getting access to machines that move: lab robots, industrial controllers, infrastructure runbooks. The usual safety layer is a sentence in the system prompt. The model can misread that sentence, be argued out of it, or ignore it, and an agent can produce a plausible key sequence that is simply wrong.

Apollo-26 looks at how to let an LLM agent press buttons on a critical machine without trusting the LLM.

## Who it is for

Teams that connect agents to operational or physical systems and need a boundary they can audit: robotics, lab automation, OT/ICS, and on-call runbooks. Apollo-26 is a reference implementation of that boundary. It is not a product for spacecraft.

## What it does

The system stitches three eras together:

1. 2026 ground station. A static Next.js page (`/ground`) signs a 34-byte frame (sequence number, truncated HMAC-SHA256, CRC-16/CCITT-FALSE) with Web Crypto and plays it as 300-baud Bell-202 FSK. By default it sends three identical bursts.
2. 1970s modem. A Python daemon receives the audio (microphone, WAV file, or loopback), demodulates it with its own NumPy modem, and validates sync → CRC → HMAC → replay → ranges. The daemon logs rejected frames, and they never reach the agent.
3. Kiro agent. A Flight Watch session over MCP calls `await_telemetry_frame` → `inspect_agc_status` → `plan_dsky_sequence` → `execute_dsky_sequence`.
4. Code-enforced gate. `mcp_server/safety_gate.py` and an independent guard in the daemon allow only the canonical key sequence for that frame, on a fresh AGC snapshot. Critical commands (P40 burn, V37/V34 during P40) also need a separate operator AUTH frame, which is bound to the command's sequence number and can be used once.
5. 1969 computer. An AGC-faithful subset emulator (15-bit ones' complement words, DSKY state machine, P00/P40, V25/V34/V37) presses the keys at ≥100 ms cadence. The mission console (`/console`) shows its real state over a local WebSocket.

## How we built it with Kiro

`docs/kiro-writeup.md` answers each of Devpost's Kiro questions. In short:

- Specs for four subsystems (`.kiro/specs/`): EARS requirements → design → tasks. Requirement and property IDs appear in test names.
- Steering (`.kiro/steering/`) holds the allowed and banned claims, module boundaries, the agent's Flight Watch rules S-01 to S-07, and the design tokens.
- Hooks (`.kiro/hooks/`): a PreToolUse guard that blocks the agent's shell while Flight Watch is live, fast property tests on Python save, and tests after spec tasks.
- MCP: a six-tool Flight Watch server. `execute_dsky_sequence` is never auto-approved, and a test enforces that.
- Property-based testing: Hypothesis P1 to P8 and fast-check P9 against shared golden vectors.

## Challenges

Running the agent live against the real MCP server found three bugs that the unit tests did not:

- Every plan came back `INSPECTION_STALE`. Agent tool calls were 5 to 30 s apart, and the inspection window was 5 s. We widened it to 20 s and kept the exact AGC state-revision check.
- Execution stopped at key 2 of 29. On Windows with Python 3.12, `time.monotonic` has 15.625 ms resolution, so 10 of 40 measured 100 ms sleeps lasted 93 to 94 ms, under the AGC's cadence rule. The fix is a high-resolution clock plus a real-clock regression test. The gate halted safely, and nothing ran out of order.
- The AUTH hold window (30 s) could never fit a human operator plus several agent calls. It is now 120 s. Key, binding, single use, and ordering are unchanged.

Most of the work went into the acoustic channel. The first test (laptop speaker into its own microphone array) decoded **0 of 20** frames, because Windows voice processing faded the steady 1200 Hz preamble by about 35 dB within two seconds. With audio enhancements off, the strict decoder still accepted only **3 of 20**: one ambiguous symbol out of 340 was enough to lose a frame. We recorded real bursts, built a channel model from them, and added a soft-decision fallback. It band-limits the audio, detects tones at mid-symbol, compensates for twist measured on the sync word, re-aligns each byte, combines up to three repeated copies, and flips at most the 8 weakest bits until CRC matches. CRC only selects a candidate; HMAC and replay checks still decide. With the fallback, the live daemon accepted **19 of 20** frames over the air on the same laptop.

## Accomplishments

- Live Kiro run of a critical P40 command: held without AUTH, refused with `AUTH_REQUIRED`, then executed 36/36 keys after the operator AUTH arrived, with R1/R2/R3 = 1250/420/3120 on the DSKY.
- Over the air, live daemon, same laptop's speaker and microphone, enhancements off: 19/20 frames accepted, median 1.95 s from first tone to accepted frame.
- Loopback path: 20/20 frames accepted, median 0.59 s from upload to validated inbox record.
- Daemon idle while listening: 6.3% of one core, about 54 MB working set.
- A browser demo at `/demo` lets anyone play the agent with no install. Its planner and DSKY are TypeScript ports that must reproduce vectors generated by the Python code.
- 146 Python tests and 96 frontend tests pass. No test or trial accepted a corrupted, forged, or replayed frame.

## What we learned

The agent's latency is part of the protocol. Time windows sized for fast code callers broke as soon as an LLM was in the loop. We widened the windows and left the exact state checks as strict as before. The radio side went the same way: the decoder now tolerates worse audio, and the acceptance rule is no weaker.

## What's next

- Phone → laptop decode trial at 0.5 m (target ≥95% of 20 frames).
- Bring the agent path toward the 10 s target (one live run took 84 s, including a deliberate refused attempt).
- Package the safety gate as a standalone MCP pattern that can sit in front of other actuators.
- Optional adapter to the real yaAGC as a separate process.

## Honest limits

The command path (daemon, MCP server, emulator) binds only to 127.0.0.1, but the Kiro agent uses a cloud LLM. The acoustic channel can be overheard and jammed; HMAC prevents forgery, not eavesdropping. The over-the-air result comes from one laptop's own speaker and microphone a few centimetres apart. The emulator is a subset, not Apollo flight software.

## Built with

Python 3.12, NumPy, sounddevice, aiohttp, jsonschema, MCP Python SDK, Hypothesis, pytest, Next.js (static export), TypeScript, Tailwind CSS, Web Audio, Web Crypto, fast-check, Kiro (specs, steering, hooks, MCP).

## Links

- Repository: https://github.com/0xshalah/apollo-26
- Browser demo, no install (GitHub Pages): https://0xshalah.github.io/apollo-26/demo/
- Ground station (GitHub Pages): https://0xshalah.github.io/apollo-26/ground/
- Video: _add the public YouTube link_
