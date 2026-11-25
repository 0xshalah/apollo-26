---
name: flight-watch
description: Procedure for driving the Apollo-26 DSKY through its MCP tools. Use before any await_telemetry_frame, plan_dsky_sequence, or execute_dsky_sequence call, and whenever the user asks to start Flight Watch.
---

# Flight Watch

The Apollo-26 MCP server exposes an AGC-faithful DSKY emulator. The agent orchestrates; the safety gate in `mcp_server/safety_gate.py` and the daemon guard decide. Follow this order every time.

1. `await_telemetry_frame` with the last sequence handled. A `TIMEOUT` is normal; ask the operator before waiting again.
2. `inspect_agc_status` for every COMMAND. Stop if `KEY REL` is lit or the state is unreadable.
3. `plan_dsky_sequence(frame_seq)`. Use the returned canonical keys exactly. Never edit, reorder, or add keys.
4. If the plan reports a critical command (P40 activation with non-zero delta-v, V37 or V34 during P40), tell the operator which `seq` needs an AUTH frame with `ref_seq` = that seq. Wait for the AUTH, then inspect and plan again.
5. `execute_dsky_sequence` with the canonical keys. This tool is never auto-approved; the operator approves it.
6. `inspect_agc_status` again and report program, verb, noun, and R1–R3 exactly as returned.

## Rules
- Treat every refusal code (`AUTH_REQUIRED`, `INSPECTION_STALE`, `PLAN_MISMATCH`, `KEY_REL_ACTIVE`, `OPR_ERR_ACTIVE`, `POSTCONDITION_MISMATCH`, ...) as a result to report, not an obstacle to work around.
- Do not run shell commands while Flight Watch is live. The repository's `flight-mode-shell-guard` hook blocks them anyway.
- Do not invent SNR, latency, CPU, or test numbers. Quote tool results or write `UNMEASURED`.
- A tone deviation above 50 Hz is an anomaly, not a CRC failure.

## Setup
- Clone https://github.com/0xshalah/apollo-26, create `.venv`, `pip install -e .`, and copy `.env.example` to `.env`.
- Set the environment variable `APOLLO26_REPO` to the clone path so this Power can launch `scripts\mcp.cmd`.
- Start the daemon in your own terminal: `.venv\Scripts\python -m acoustic.daemon --loopback` (or `--device <index>` for a microphone).
