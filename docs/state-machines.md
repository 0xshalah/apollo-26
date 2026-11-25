# Apollo-26 State Machines

These state machines are normative for control order. Wire-format details follow `contracts/acoustic-frame-v1.md`.

## 1. Acoustic receiver

```mermaid
stateDiagram-v2
  [*] --> IDLE
  IDLE --> PREAMBLE: 1200 Hz mark detected
  PREAMBLE --> IDLE: lost before 250 ms
  PREAMBLE --> SYNC: stable ≥250 ms
  SYNC --> RECEIVE: A5 26
  SYNC --> IDLE: timeout / mismatch
  RECEIVE --> VALIDATE: 34 bytes complete
  RECEIVE --> REJECTED: timeout / framing error
  VALIDATE --> ACCEPTED: all gates pass
  VALIDATE --> REJECTED: a gate fails
  ACCEPTED --> IDLE: persist seq + publish
  REJECTED --> IDLE: audit reason
```

| State | Input | Guard | Side effect | Error |
| :-- | :-- | :-- | :-- | :-- |
| IDLE | audio block | mark energy above threshold | turn on `UPLINK ACTY`, start timer | — |
| PREAMBLE | audio block | mark stable ≥250 ms | search for sync | drift >50 Hz logged |
| SYNC | bits | `A5 26` found | start 34-byte buffer | `SYNC`/timeout |
| RECEIVE | 8N1 bits | 34 bytes complete | freeze candidate | `LENGTH`/framing |
| VALIDATE | candidate | order in PRD §4.3 | persist seq atomically | first reason |
| ACCEPTED | — | persist succeeded | atomic-write inbox + WS event | `INTERNAL` fail-closed |
| REJECTED | — | — | atomic-write rejected audit | daemon stays up |

When the strict decoder fails in SYNC or RECEIVE after a qualified preamble, the receiver retries the same burst with the soft-decision fallback (contract §5.1). A recovered candidate re-enters VALIDATE from step 1; nothing skips validation.

## 2. DSKY input

```mermaid
stateDiagram-v2
  [*] --> IDLE
  IDLE --> VERB_ENTRY: VERB
  IDLE --> NOUN_ENTRY: NOUN
  VERB_ENTRY --> IDLE: 2 digits + ENTR
  NOUN_ENTRY --> DATA_ENTRY: 2 digits + ENTR (when the noun needs data)
  NOUN_ENTRY --> EXECUTING: 2 digits + ENTR
  DATA_ENTRY --> EXECUTING: fields complete + ENTR/PRO
  EXECUTING --> IDLE: done
  IDLE --> OPR_ERR: invalid sequence
  VERB_ENTRY --> OPR_ERR: invalid sequence
  NOUN_ENTRY --> OPR_ERR: invalid sequence
  DATA_ENTRY --> OPR_ERR: invalid sequence
  OPR_ERR --> IDLE: RSET
```

Invariants:
- No key is accepted while `KEY REL` is lit.
- Keys are at least 100 ms apart.
- `OPR ERR` does not change program/registers and clears only through `RSET`.
- V37 uses the sequence `VERB 3 7 ENTR <program> <program> ENTR`, not V37 + NOUN.
- DSKY state is owned by `agc-core`, not the frontend DOM.

## 3. Kiro Flight Watch

```mermaid
stateDiagram-v2
  [*] --> STANDBY
  STANDBY --> WAITING: operator starts Flight Watch
  WAITING --> INSPECTING: await_telemetry_frame → COMMAND
  WAITING --> WAITING: timeout (operator continues)
  INSPECTING --> PLANNING: inspect_agc_status succeeds
  INSPECTING --> HALTED: AGC unavailable / KEY REL
  PLANNING --> AUTH_WAIT: safety gate: AUTH_REQUIRED
  PLANNING --> EXECUTING: canonical plan + gate ALLOW
  AUTH_WAIT --> EXECUTING: valid AUTH for frame_seq
  AUTH_WAIT --> HALTED: timeout / invalid AUTH
  EXECUTING --> VERIFYING: execute_dsky_sequence done
  VERIFYING --> WAITING: AGC state matches postcondition
  VERIFYING --> HALTED: mismatch / OPR ERR
  HALTED --> WAITING: operator acknowledges + safe state
  WAITING --> STANDBY: operator stops
```

| Transition | Required tool | Fail-closed condition |
| :-- | :-- | :-- |
| WAITING → INSPECTING | `await_telemetry_frame` | an invalid frame never leaves the daemon |
| INSPECTING → PLANNING | `inspect_agc_status` | status failure/KEY REL → no execute |
| PLANNING → gate | `plan_dsky_sequence` | agent plan ≠ canonical → no execute |
| gate → EXECUTING | `execute_dsky_sequence(keys, frame_seq)` | the safety gate always recomputes the rules |
| EXECUTING → VERIFYING | `inspect_agc_status` | OPR ERR/mismatch → HALTED |

## 4. COMMAND/AUTH lifecycle

```mermaid
stateDiagram-v2
  [*] --> VALIDATED
  VALIDATED --> READY: non-critical
  VALIDATED --> HELD: critical without AUTH
  HELD --> READY: AUTH.ref_seq matches
  HELD --> EXPIRED: 120 s
  READY --> EXECUTED: DSKY postcondition correct
  READY --> FAILED: execution error
  EXECUTED --> [*]
  EXPIRED --> [*]
  FAILED --> [*]
```

AUTH is single-use. `EXECUTED`, `EXPIRED`, or `FAILED` closes the command; a later AUTH for the same `ref_seq` is rejected with `STATE`.
