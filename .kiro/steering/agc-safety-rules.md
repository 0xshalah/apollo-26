---
inclusion: always
---

# AGC Safety Rules

This steering guides the agent. Normative enforcement stays in `mcp-server/safety_gate.py` and is verified by P7.

## S-01 — Tool boundary
While Flight Watch is active, use only the Apollo-26 MCP tools. Do not run shell commands or change project files. The `flight-mode-shell-guard` hook is an extra layer.

## S-02 — Inspect before act
Before `execute_dsky_sequence`, call `inspect_agc_status`. Refuse or wait if `KEY REL` is lit or the AGC state cannot be read.

## S-03 — Canonical plan
Call `plan_dsky_sequence(frame_seq)` and compare it with the agent's plan. Execute only the canonical sequence for that frame.

## S-04 — Critical authorization
The following commands need a valid `AUTH` whose `ref_seq` equals the `COMMAND` sequence:
- V37 while P40 is active.
- V34 while P40 is active.
- P40 activation with `abs(delta_v)` above the threshold set by the `mcp-bridge` spec.

AUTH must validate with `APOLLO26_OPERATOR_KEY`, must not have been used before, and the AUTH sequence must be newer than the last sequence.

## S-05 — Key cadence
Send keys only while `KEY REL` is off, at least 100 ms apart. Stop the sequence if `OPR ERR` lights.

## S-06 — Anomaly reporting
A tone deviation above 50 Hz is an anomaly that must be reported. Do not call it a CRC failure unless CRC actually failed. Accept/reject decisions follow the frame contract and the acoustic-link spec.

## S-07 — No invented evidence
Do not make up SNR, latency, CRC rate, PBT counts, RAM, or CPU values. Take them only from tools/status/reports. If none exist, show `UNMEASURED`.
