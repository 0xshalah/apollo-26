---
inclusion: always
---

# Apollo-26 Product Context

## Pitch
**Agent safety for physical systems.** When an LLM agent is allowed to press buttons on a machine that moves, burns, or doses something, the prompt cannot be the safety layer. Apollo-26 shows a pattern where the agent only orchestrates and code decides: authenticated input, inspect-before-act, a canonical plan the agent must match exactly, a separate human AUTH for critical actions, and an independent guard at the actuator.

The 1969 Apollo Guidance Computer is the test bench: a real control interface (VERB/NOUN keys on a DSKY), a critical action (the P40 engine burn), and an input channel with no IP stack (Bell-202 audio).

## Audience
Teams that connect AI agents to operational or physical systems: robotics, lab instruments, industrial control (OT/ICS), and infrastructure runbooks.

## Goal
Demonstrate an emergency command path without an IP interface: the ground station transmits a Bell-202 frame as sound, the daemon validates it, a Kiro agent plans DSKY input through MCP, and the AGC subset emulator executes it only after the safety gate allows it.

## Main scenario
A browser ground station (phone or laptop) transmits an authenticated `COMMAND` → laptop microphone → daemon → Kiro Flight Watch session → MCP safety gate → DSKY P40.

## Decision priorities
1. Safety and protocol correctness.
2. A real, repeatable end-to-end flow.
3. Evidence of Kiro use (Specs, Steering, Hooks, MCP, PBT, custom agent, Power).
4. UI and presentation.

## Allowed claims
- The daemon–MCP–AGC command path has no socket outside `127.0.0.1` once verified.
- Frames use CRC-16 for integrity, truncated HMAC-SHA256 for demo authentication, and a sequence counter against replay.
- Performance numbers may only be stated as `target`, `measured`, or `verified`, following `docs/evidence-matrix.md`.
- The emulator is an AGC-faithful subset, not the real AGC flight software.
- The safety pattern is general; Apollo-26 implements it for one emulated machine. Do not claim it is deployed on real physical systems.

## Banned claims
Do not write "100% immune", "exploit-free", "100% CRC", "0 dB attack surface", "100% offline", or any test number that was not measured. Kiro uses a cloud LLM; an offline claim applies only to the local command path.

## v1 scope
- 300 baud only.
- Simple P00 and P40 programs.
- VERB V25, V34, and V37 only.
- Does not run Luminary 99 or Colossus 249.
- The landing page at `/` was approved by the operator on 12 Nov 2026 before the phone → laptop path worked. Condition: status is written honestly in the hero and FAQ, and every number is read from `docs/metrics.json` / `docs/test-summary.json`, including missed targets.

Product source of truth: `PRD.md`. Schedule and decisions: `TASK.md`.
