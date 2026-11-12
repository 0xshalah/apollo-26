# Requirements Document

## AGC Emulator

## Introduction

The `agc-emulator` feature is the pure-Python Apollo-26 domain core for a deliberately limited, AGC-faithful demonstration. It models 15-bit words, erasable memory and registers, DSKY input, and simplified P00/P40 behavior. It does not run Luminary 99, Colossus 249, or a general AGC instruction set.

`agc-core` owns all AGC and DSKY state. The acoustic daemon may host and drive the core through adapters, the MCP server may inspect or command it through daemon-owned local RPC, and the web dashboard may only project snapshots.

## Glossary

- **Data word**: A 15-bit AGC ones' complement value in bits 14 through 0.
- **Physical word**: A 16-bit representation containing one odd-parity bit in bit 15 and the data word in bits 14 through 0.
- **Positive zero (`+0`)**: Data pattern `0x0000`.
- **Negative zero (`-0`)**: Data pattern `0x7FFF`.
- **End-around carry**: Ones' complement addition in which a carry beyond bit 14 is added back into bit 0 until no carry remains.
- **Engine**: The pure domain object that owns erasable memory, machine registers, programs, DSKY state, and lamps.
- **DSKY state**: One of `IDLE`, `VERB_ENTRY`, `NOUN_ENTRY`, `DATA_ENTRY`, `EXECUTING`, or `OPR_ERR`.
- **Accepted key**: A key event that passes the `KEY REL`, cadence, timestamp, and current-state guards and is then applied to the DSKY state machine.
- **Display register**: One of the signed DSKY values R1, R2, or R3; it is distinct from machine registers A, L, Q, and Z.
- **Canonical V37 sequence**: `VERB 3 7 ENTR p1 p2 ENTR`, where `p1 p2` is `00` or `40`.
- **Snapshot**: An immutable, deterministic value object containing one coherent view of the Engine state.

## Requirements

### AGC-REQ-1: 15-bit word and odd parity

**User Story:** As an emulator developer, I want a single valid word representation so arithmetic, memory, and inspection agree on every bit pattern.

#### Acceptance Criteria

1. THE word domain SHALL preserve exactly 15 data bits and SHALL reject data input outside `0x0000..0x7FFF` instead of truncating it.
2. WHEN a Physical word is created from a Data word, THE word domain SHALL set bit 15 so the population count of all 16 bits is odd.
3. WHEN a Physical word is decoded, THE word domain SHALL reject values outside `0x0000..0xFFFF` or values whose 16-bit population count is even.
4. WHEN a valid Physical word is decoded and encoded again, THE word domain SHALL return the identical 16-bit pattern.
5. THE word domain SHALL preserve `+0` and `-0` as distinct raw Data word values throughout construction, storage, negation, arithmetic results, and snapshots.

### AGC-REQ-2: Ones' complement arithmetic

**User Story:** As a flight-computer reviewer, I want arithmetic to follow explicit ones' complement rules, including both zero representations.

#### Acceptance Criteria

1. WHEN a Data word is negated, THE word domain SHALL complement all 15 data bits and SHALL therefore map `+0` to `-0` and `-0` to `+0`.
2. WHEN two Data words are added, THE word domain SHALL add their 15-bit patterns, apply end-around carry until no carry remains, and return a valid odd-parity result.
3. FOR ALL valid Data words `x`, WHEN `x` is added to its bitwise complement, THE result SHALL be raw `-0` (`0x7FFF`).
4. FOR ALL valid Data words `x` and `y`, WHEN the operands are added in either order, THE raw result and overflow indication SHALL be identical.
5. WHEN two nonzero operands with the same mathematical sign produce a nonzero result with the opposite sign after end-around carry, THE addition result SHALL report overflow; OTHERWISE THE addition result SHALL not report overflow.
6. WHEN a Data word is converted to a mathematical integer, THE word domain SHALL map positive magnitudes to `0..16383`, negative magnitudes to `-1..-16383`, and SHALL require an explicit zero-sign value when the caller needs to distinguish `+0` from `-0`.

### AGC-REQ-3: Erasable memory and machine registers

**User Story:** As an emulator developer, I want bounded typed storage so invalid addresses and malformed words cannot enter machine state.

#### Acceptance Criteria

1. THE Engine SHALL provide exactly 2048 erasable-memory addresses numbered `0..2047`.
2. THE Engine SHALL provide distinct machine registers A, L, Q, and Z, each storing one valid Physical word.
3. WHEN erasable memory or a machine register is written, THE Engine SHALL accept only a validated word-domain value and SHALL preserve its complete Data word and parity representation.
4. WHEN a valid memory address or register is read after a successful write, THE Engine SHALL return the identical word value that was written.
5. IF a memory address is outside `0..2047` or a register identifier is not A, L, Q, or Z, THEN THE Engine SHALL reject the operation with a stable domain error and SHALL leave all Engine state unchanged.

### AGC-REQ-4: Deterministic reset state

**User Story:** As a test author, I want every Engine instance to start identically so examples and generated state-machine runs are reproducible.

#### Acceptance Criteria

1. WHEN an Engine is created, THE Engine SHALL initialize all 2048 memory words and registers A, L, Q, and Z to raw `+0` with valid odd parity.
2. WHEN an Engine is created, THE Engine SHALL initialize program P00, DSKY state `IDLE`, blank pending input, display values R1-R3 at positive zero, all activity/error lamps off, and no accepted-key timestamp.
3. WHEN two Engines receive equal validated inputs, equal injected times, and equal scheduler ticks in the same order, THE Engines SHALL produce equal operation results and equal snapshots at every step.

### AGC-REQ-5: DSKY key vocabulary and entry state

**User Story:** As an operator, I want the subset DSKY to recognize the approved keyboard while exposing its current input state.

#### Acceptance Criteria

1. THE DSKY SHALL define typed keys for `VERB`, `NOUN`, digits `0..9`, `PLUS`, `MINUS`, `ENTR`, `PRO`, `CLR`, `RSET`, and `KEY_REL`.
2. WHEN `VERB` is accepted in `IDLE`, THE DSKY SHALL enter `VERB_ENTRY` with an empty two-digit verb buffer.
3. WHEN `NOUN` is accepted in `IDLE`, THE DSKY SHALL enter `NOUN_ENTRY` with an empty two-digit noun buffer.
4. WHEN `CLR` is accepted during an entry state, THE DSKY SHALL remove the most recently entered sign or digit from the active field without changing the program or committed display registers.
5. WHEN `KEY_REL` is accepted while the `KEY REL` lamp is off, THE DSKY SHALL cancel pending input, clear transient VERB/NOUN entry displays, and return to `IDLE` without changing the active program or committed R1-R3 values.
6. WHEN any accepted key changes DSKY state, THE next Snapshot SHALL expose the resulting state and pending input deterministically.

### AGC-REQ-6: KEY REL and key cadence guards

**User Story:** As a safety integrator, I want key timing and display-busy guards enforced by the core rather than by callers alone.

#### Acceptance Criteria

1. WHILE the `KEY REL` lamp is on, THE DSKY SHALL reject every key event without changing DSKY state, pending input, active program, display registers, lamps, or the last-accepted-key timestamp.
2. WHEN no key has previously been accepted, THE DSKY SHALL allow a key at any nonnegative injected monotonic time if all other guards pass.
3. WHEN a key event occurs less than 100 milliseconds after the last Accepted key, THE DSKY SHALL reject it with `KEY_CADENCE` and SHALL leave all Engine state unchanged.
4. WHEN a key event occurs exactly 100 milliseconds or more after the last Accepted key, THE DSKY SHALL allow it to proceed to state-machine validation if all other guards pass.
5. IF an injected key timestamp is negative or earlier than the last Accepted key timestamp, THEN THE DSKY SHALL reject it with `TIME_REGRESSION` and SHALL leave all Engine state unchanged.
6. WHEN a key attempt is rejected by a timing or `KEY REL` guard, THE DSKY SHALL calculate the next cadence guard from the last Accepted key rather than from the rejected attempt.

### AGC-REQ-7: Invalid sequence and OPR ERR recovery

**User Story:** As an operator, I want malformed DSKY input to fail visibly without partially changing the active program or committed values.

#### Acceptance Criteria

1. IF an Accepted key is not legal in the current DSKY state or makes the active field invalid, THEN THE DSKY SHALL enter `OPR_ERR`, turn on the `OPR ERR` lamp, and preserve the active program, R1-R3, memory, and machine registers as they were before that key.
2. WHILE the DSKY is in `OPR_ERR`, THE DSKY SHALL reject every otherwise Accepted key except `RSET` with `OPR_ERR_LATCHED` and SHALL preserve the latched state.
3. WHEN `RSET` passes the `KEY REL` and cadence guards while the DSKY is in `OPR_ERR`, THE DSKY SHALL clear the `OPR ERR` lamp, clear pending input, and return to `IDLE` without changing the active program or committed R1-R3 values.
4. WHEN `RSET` is accepted outside `OPR_ERR`, THE DSKY SHALL clear pending input and return to `IDLE` without changing the active program or committed R1-R3 values.
5. IF a multi-key caller stops after a rejected key, THEN THE Engine SHALL expose all changes from earlier Accepted keys and SHALL apply no later keys; THE core SHALL not claim batch atomicity.

### AGC-REQ-8: Canonical V37 program change

**User Story:** As a command planner, I want one canonical program-change sequence so agents and deterministic safety code can compare the same keys.

#### Acceptance Criteria

1. WHEN the exact sequence `VERB 3 7 ENTR 0 0 ENTR` is accepted from `IDLE`, THE DSKY SHALL activate P00 and return to `IDLE`.
2. WHEN the exact sequence `VERB 3 7 ENTR 4 0 ENTR` is accepted from `IDLE`, THE DSKY SHALL activate simplified P40 and return to `IDLE`.
3. IF a V37 sequence includes `NOUN`, contains a program other than `00` or `40`, contains the wrong number of program digits, or deviates from the canonical ordering, THEN THE DSKY SHALL apply AGC-REQ-7 and SHALL not change the active program.
4. WHEN V37 changes the active program successfully, THE DSKY SHALL display `37` as the last completed verb and the two-digit active program in the PROG display.

### AGC-REQ-9: V25 three-component load

**User Story:** As a ground-command planner, I want a bounded three-component load that commits R1-R3 only after the complete input is valid.

#### Acceptance Criteria

1. WHEN `VERB 2 5 ENTR` and the configured Apollo-26 P40 noun are accepted from `IDLE`, THE DSKY SHALL enter `DATA_ENTRY` and request R1, R2, and R3 in that order.
2. WHEN a data component is entered, THE DSKY SHALL require exactly one explicit sign followed by one to five decimal digits and termination by `ENTR` for R1/R2 or by `ENTR` or `PRO` for R3.
3. WHEN all three components are within `-16383..16383` and the final terminator is accepted, THE DSKY SHALL atomically commit their signed values to R1-R3, preserve explicit negative zero where entered, display `25` and the configured noun, and return to `IDLE`.
4. IF a V25 field is incomplete, has more than five digits, has no sign, repeats a sign, or represents a magnitude above 16383, THEN THE DSKY SHALL apply AGC-REQ-7 and SHALL leave all three committed display registers unchanged.
5. THE configured Apollo-26 P40 noun SHALL be a typed constant documented in `design.md`; THE implementation SHALL NOT accept arbitrary nouns for V25.

### AGC-REQ-10: V34 termination

**User Story:** As an operator, I want a canonical termination verb for leaving the simplified burn program safely.

#### Acceptance Criteria

1. WHEN `VERB 3 4 ENTR` is accepted while P40 is active, THE DSKY SHALL terminate P40, activate P00, turn off periodic `COMP ACTY`, preserve committed R1-R3, display `34` as the last completed verb, and return to `IDLE`.
2. WHEN `VERB 3 4 ENTR` is accepted while P00 is active, THE DSKY SHALL remain in P00, preserve committed R1-R3, display `34` as the last completed verb, and return to `IDLE`.
3. IF a V34 sequence supplies a NOUN or data field, THEN THE DSKY SHALL apply AGC-REQ-7 and SHALL not change the active program or committed R1-R3.

### AGC-REQ-11: Simplified P00

**User Story:** As an operator, I want a deterministic idle program that provides a safe baseline.

#### Acceptance Criteria

1. WHILE P00 is active, THE Engine SHALL accept supported DSKY entry but SHALL perform no autonomous mutation of R1-R3, erasable memory, or machine registers.
2. WHILE P00 is active, THE Engine SHALL keep scheduler-driven `COMP ACTY` off.
3. WHEN P00 is entered through reset construction, V37, or V34, THE Engine SHALL preserve committed R1-R3 unless the initiating requirement explicitly states otherwise.

### AGC-REQ-12: Simplified P40 and display values

**User Story:** As a demonstration operator, I want P40 to show the three validated maneuver inputs without pretending to execute Apollo flight software.

#### Acceptance Criteria

1. WHILE P40 is active after a completed V25 load, THE DSKY SHALL display R1 as Apollo-26 azimuth in centidegrees, R2 as elevation in centidegrees, and R3 as delta-v in tenths of feet per second.
2. WHEN P40 becomes active before any V25 load has completed, THE DSKY SHALL display the previously committed R1-R3 values and SHALL not invent maneuver data.
3. WHEN validated boundary input cannot be represented in the DSKY range `-16383..16383`, THE Engine SHALL reject it with `DISPLAY_RANGE` rather than truncate, wrap, or convert it with floating-point arithmetic.
4. THE Engine SHALL identify P40 as a simplified Apollo-26 program and SHALL NOT expose state or metadata that claims Luminary 99 or Colossus 249 execution.

### AGC-REQ-13: Lamps and scheduler ticks

**User Story:** As a console operator, I want lamp state to follow explicit domain events and deterministic scheduler ticks.

#### Acceptance Criteria

1. WHILE P40 is active, WHEN the Engine receives an injected scheduler tick at a configured `COMP ACTY` boundary, THE Engine SHALL toggle `COMP ACTY` exactly once for that boundary.
2. WHILE P00 is active, WHEN the Engine receives any scheduler tick, THE Engine SHALL keep `COMP ACTY` off.
3. WHEN the daemon reports validated receiver activity through an explicit typed Engine input, THE Engine SHALL set `UPLINK ACTY` to that supplied boolean without reading audio or network state itself.
4. WHEN an explicit typed display-busy input changes, THE Engine SHALL set `KEY REL` to that supplied boolean without reading a clock, scheduler, filesystem, microphone, or network itself.
5. IF scheduler ticks are duplicated, earlier than the previous tick, or not on a pending boundary, THEN THE Engine SHALL return a stable scheduler error and SHALL leave all state unchanged.

### AGC-REQ-14: Deterministic snapshots

**User Story:** As an MCP and WebSocket adapter developer, I want coherent snapshots that can be compared and serialized without reading mutable internals.

#### Acceptance Criteria

1. WHEN a Snapshot is requested, THE Engine SHALL return one immutable value containing a monotonically increasing revision, active program, DSKY state, displayed verb and noun, pending input, raw and signed views of R1-R3, raw Physical words for A/L/Q/Z, and `COMP ACTY`, `UPLINK ACTY`, `KEY REL`, and `OPR ERR` lamp states.
2. WHEN no successful state mutation has occurred between two Snapshot requests, THE Engine SHALL return Snapshots with equal revisions and equal field values.
3. WHEN one accepted input or scheduler tick mutates state, THE Engine SHALL increment the revision exactly once and SHALL publish all effects in one coherent Snapshot.
4. WHEN two equal operation histories are replayed from reset, THE Engine SHALL produce field-for-field equal Snapshots without embedding wall-clock time, object identity, random values, or unordered collections.
5. WHERE an adapter serializes a Snapshot across a process boundary, THE adapter SHALL validate its JSON once against the applicable contract and SHALL preserve raw zero sign separately from the signed integer projection.

### AGC-REQ-15: Pure domain boundary and stable errors

**User Story:** As a maintainer, I want the emulator isolated from I/O and failures represented consistently across adapters.

#### Acceptance Criteria

1. THE `agc-core` implementation SHALL NOT import or implicitly access audio, filesystem, environment variables, wall or monotonic clocks, schedulers, network, MCP, React, or browser APIs.
2. WHERE time or periodic behavior is required, THE domain API SHALL receive validated monotonic timestamps or typed scheduler ticks from an injected daemon adapter.
3. THE public domain API SHALL use Python type hints and typed values such as enums, frozen dataclasses, and domain result types instead of free-form strings or dictionaries.
4. WHEN a domain operation fails, THE Engine SHALL return or raise one typed error with a stable code from `PARITY`, `WORD_RANGE`, `ADDRESS_RANGE`, `REGISTER`, `KEY_REL_ACTIVE`, `KEY_CADENCE`, `TIME_REGRESSION`, `INVALID_KEY_SEQUENCE`, `OPR_ERR_LATCHED`, `UNSUPPORTED_VERB`, `UNSUPPORTED_NOUN`, `UNSUPPORTED_PROGRAM`, `DISPLAY_RANGE`, or `SCHEDULER_STATE` and SHALL include mutable human-readable detail separately.
5. IF an adapter translates a domain failure across RPC or WebSocket, THEN THE adapter SHALL preserve the stable code and SHALL not use the human-readable message as machine control data.
6. THE Engine SHALL NOT authorize critical commands, validate HMAC or sequence counters, demodulate audio, persist state, serve HTTP/WebSocket, or decide MCP safety policy.

## Out of Scope

- A general AGC instruction decoder or execution cycle.
- Fixed memory, bank switching, interrupts, telemetry downlink, or actual SPS dynamics.
- Luminary 99, Colossus 249, yaAGC embedding, or claims of flight-software equivalence.
- V06, V16, V35, or any verb other than V25, V34, and V37.
- Authorization decisions for V37, V34, or high-delta-v commands; those belong to `mcp-server/safety_gate.py` and P7.
- Audio, persistence, network servers, RPC transport, and WebSocket serialization implementations.

## Traceability and Source Priority

1. `docs/state-machines.md` controls DSKY states, `KEY REL`, cadence, `OPR ERR`, and canonical V37 ordering.
2. `PRD.md` v2.3.0 controls the feature scope, FR-10 through FR-12, P8, and the AGC-faithful-subset claim.
3. `TASK.md` controls M3 dependencies and its acceptance gate.
4. `docs/evidence-matrix.md` controls verification status and evidence wording.
5. `.kiro/steering/structure.md`, `.kiro/steering/tech.md`, `.kiro/steering/product.md`, and `.kiro/steering/agc-safety-rules.md` control module boundaries, dependency direction, injected I/O, stable errors, and safety ownership.
6. `design.md` records feature-level choices where the higher-priority sources intentionally leave details open.
