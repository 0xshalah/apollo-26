# Implementation Plan: MCP Bridge

**Feature:** `mcp-bridge`  
**Status:** Draft; no implementation or hook is created by this plan  
**External prerequisites:** `TASK.md` 2.7 (durable daemon sequence) and 3.8 (daemon/AGC local RPC) must be complete. Exact V25/V34/V37 command semantics from M3.1/M3 must be approved before planner work.

## Overview

This plan decomposes the approved MCP bridge design into contract, domain, adapter, safety, hook, property-test, and end-to-end work. It preserves parallel work where dependencies allow and ends at the M4 validation gate.

## Notes

- Complete dependencies before starting a task; independent tasks may run in parallel.
- Do not mark a task complete because code exists. Run its listed validation and preserve output plus exit code.
- Use typed domain values and injected clock, filesystem, environment, and RPC adapters.
- Keep edits within the ownership boundaries in `design.md`; do not import `agc-core` or `acoustic.frame` into `mcp-server`.
- Never weaken the normative frame contract, SafetyGate, P7, AUTH one-time behavior, or no-auto-approve policy to make a test pass.
- Task test names should include requirement/property IDs where practical, for example `test_mcp_req_10_rejects_noncanonical_plan` and `test_p7_critical_without_auth_never_actuates`.

## Tasks

- [ ] 1. Establish Python test and validation scaffold
  - Add the Python 3.12 project/test configuration required to run focused, quick, and full pytest profiles if it does not already exist.
  - Register `slow` and property-test profiles without reducing the full P7 target.
  - Provide a test-report helper that stores command, timestamps, seed where applicable, output, and exit code.
  - Requirements: MCP-REQ-23, MCP-REQ-27, MCP-REQ-28, MCP-REQ-29
  - Design: §14 Test strategy
  - Dependencies: external M0.1–M0.2
  - Validation:
    - `python -m pytest -m "not slow"` exits successfully, even if only scaffold tests exist.
    - `python -m pytest` exits successfully.
    - A deliberately failing fixture proves the report preserves a nonzero exit code; remove/disable that fixture afterward.

- [ ] 2. Define cross-process contracts and shared catalog
  - Requirements: MCP-REQ-2, MCP-REQ-6, MCP-REQ-7, MCP-REQ-9, MCP-REQ-23, MCP-REQ-25, MCP-REQ-31
  - Design: §§5–8, §11
  - Dependencies: none for schema structure; external M3 command decisions for catalog values

  - [ ] 2.1 Define MCP tool request/result/error schemas
    - Define strict schemas for all six tools, the common result envelope, key enum, AGC snapshot, canonical plan, postcondition, and stable errors.
    - Reject extra properties, unknown versions, free-form keys, oversized arrays, and invalid sequence/range values.
    - Keep human messages non-normative and stable codes normative.
    - Requirements: MCP-REQ-3–10, MCP-REQ-20, MCP-REQ-25
    - Design: §7 MCP tool contracts; §10 Error model
    - Dependencies: none
    - Validation:
      - Positive examples for every request and success result pass schema validation.
      - Negative examples for missing fields, extra fields, invalid enum/range, and unsupported version fail before domain calls.

  - [ ] 2.2 Define daemon RPC schema
    - Add the versioned 64-KiB-bounded request/success/error envelope and six RPC methods from design §8.
    - Include request correlation, daemon instance ID, sequence epoch, deadlines, expected revision, operation ID, catalog version, and execution-journal result.
    - Requirements: MCP-REQ-2, MCP-REQ-6, MCP-REQ-16–22
    - Design: §8 Local RPC contracts
    - Dependencies: 2.1; external M3.8 interface draft
    - Validation:
      - Contract tests reject unknown methods, mismatched request IDs, extra properties, wrong epochs, and oversized messages.
      - Round-trip fixtures cover every method and error envelope.

  - [ ] 2.3 Define immutable audit-event schema
    - Define event types and required context for session, frame delivery, AUTH lifecycle, inspection, planning, gate, execution, reconciliation, postcondition, cursor, and hook validation.
    - Prohibit secret/key fields and unconstrained raw exception traces.
    - Requirements: MCP-REQ-23, MCP-REQ-25
    - Design: §11 Audit design
    - Dependencies: 2.1
    - Validation:
      - Every decision/error path has a schema-valid fixture.
      - Secret-redaction tests fail any fixture containing configured secret values.

  - [ ] 2.4 Approve the v1 DSKY command catalog
    - Encode verified V25, V34, and V37 templates, integer conversions, allowed ranges, preconditions, and postconditions in one versioned contract.
    - Include the known V37 sequence exactly as specified in `docs/state-machines.md`.
    - Define `P40_CRITICAL_DELTA_V_THRESHOLD_TENTHS_FPS = 0` once and expose it as catalog metadata.
    - Do not guess unresolved V25/V34 semantics; block this task until M3 approval exists.
    - Requirements: MCP-REQ-9, MCP-REQ-10, MCP-REQ-12, MCP-REQ-31
    - Design: §6 Canonical planning
    - Dependencies: external M3.1 and M3.8
    - Validation:
      - Catalog schema and golden examples pass.
      - Contract equality tests prove MCP and daemon use catalog version and threshold without duplicated literals.
      - Unsupported combinations and unrepresentable register values are rejected rather than clamped.

  - [ ] 2.5 Align telemetry schema conditionals
    - Add conditional constraints so accepted COMMAND requires `ref_seq=0` and accepted AUTH has zero payload fields as required by the normative frame contract.
    - Do not change 34-byte wire layout or validation order.
    - Requirements: MCP-REQ-6, MCP-REQ-13, MCP-REQ-31
    - Design: §5.3 AUTH lifecycle; §16 Risks
    - Dependencies: 1
    - Validation:
      - Existing golden telemetry remains valid.
      - AUTH with nonzero payload and COMMAND with nonzero `ref_seq` fail schema tests.
      - Normative wire vectors remain unchanged.

- [ ] 3. Implement typed domain model and injected ports
  - Requirements: MCP-REQ-6–25, MCP-REQ-31
  - Design: §§3.2, 5, 9, 10
  - Dependencies: 2.1, 2.2, 2.3

  - [ ] 3.1 Implement immutable domain values and lifecycle transitions
    - Add enums/dataclasses for sequences, epochs, revisions, keys, plans, snapshots, critical reasons, AUTH state, command state, gate decisions, and execution results.
    - Encode only allowed lifecycle transitions and make terminal/unknown states unable to return to READY.
    - Requirements: MCP-REQ-6, MCP-REQ-14–16, MCP-REQ-21
    - Design: §5 Domain model
    - Dependencies: 2.1
    - Validation:
      - Transition-table tests cover every allowed and forbidden edge.
      - Invalid values cannot construct trusted domain types.

  - [ ] 3.2 Define clock, ledger, cursor, audit, marker, and daemon RPC ports
    - Keep library code free of implicit environment, filesystem, clock, or network reads.
    - Provide deterministic fakes for tests, including a controllable monotonic/wall clock pair and concurrency barriers.
    - Requirements: MCP-REQ-16, MCP-REQ-23, MCP-REQ-31, MCP-REQ-32
    - Design: §§3.2, 9
    - Dependencies: 3.1
    - Validation:
      - Unit tests run without filesystem, network, microphone, ambient environment, or real clock.
      - Public APIs pass static type checking.

  - [ ] 3.3 Implement stable domain-error translation
    - Map schema, RPC, inspection, planning, AUTH, concurrency, execution, audit, and internal failures to design §10 codes.
    - Log unexpected exceptions with request/session context and redact secrets.
    - Requirements: MCP-REQ-25
    - Design: §10 Error model
    - Dependencies: 3.1, 3.2
    - Validation:
      - Table-driven tests exercise every stable code and retryability flag.
      - No expected safety rejection becomes generic `INTERNAL`.

- [ ] 4. Implement daemon RPC client adapter
  - Connect only to the configured loopback endpoint and validate both sides of every message once.
  - Enforce deadline, maximum size, request correlation, instance/epoch checks, and cancellation semantics.
  - Expose typed methods for telemetry read/await, AGC inspect, execution preflight/execute/get.
  - Requirements: MCP-REQ-2, MCP-REQ-5–7, MCP-REQ-16–22, MCP-REQ-31, MCP-REQ-32
  - Design: §8 Local RPC contracts
  - Dependencies: 2.2, 3.2, 3.3; external M3.8
  - Validation:
    - Integration test uses an actual loopback RPC fixture.
    - Tests reject non-loopback configuration, malformed/oversized response, request-ID mismatch, epoch change, timeout, and disconnect.
    - Network inspection records no command-path socket outside `127.0.0.1`; keep evidence status unverified until this test passes in the target environment.

- [ ] 5. Implement durable stores and immutable audit sink
  - Requirements: MCP-REQ-5, MCP-REQ-14–16, MCP-REQ-21–23, MCP-REQ-32
  - Design: §§5.2–5.4, 9, 11
  - Dependencies: 2.3, 3.2

  - [ ] 5.1 Implement cursor and Flight Watch lease store
    - Persist cursor by daemon identity/sequence epoch; atomically advance only on delivered frames.
    - Enforce one live Flight Watch lease, validate stale markers, and preserve cursor on stop/cancellation.
    - Requirements: MCP-REQ-5, MCP-REQ-22, MCP-REQ-26, MCP-REQ-32
    - Property: MCP-P6
    - Dependencies: 3.2
    - Validation:
      - Timeout/cancel leaves cursor unchanged; delivery advances exactly once.
      - Restart resumes without duplicate delivery in the same epoch.
      - A second live session receives `FLIGHT_WATCH_BUSY`.

  - [ ] 5.2 Implement transactional COMMAND/AUTH ledger
    - Persist lifecycle records and compare-and-swap claim/consume transitions by `(epoch, frame_seq)`.
    - Reject AUTH-before-COMMAND, wrong ref/provenance, duplicate AUTH, exact-deadline AUTH, and AUTH for closed commands.
    - Requirements: MCP-REQ-13–16, MCP-REQ-21, MCP-REQ-22
    - Properties: MCP-P2, MCP-P7
    - Dependencies: 3.1, 3.2
    - Validation:
      - Fake-clock tests cover `deadline-ε`, `deadline`, and `deadline+ε`.
      - Concurrent claims produce one winner and one stored result/conflict.
      - Restart and epoch-change tests cannot revive pending or consumed AUTH.

  - [ ] 5.3 Implement atomic immutable audit publication
    - Write each event through temp file plus atomic rename and derive JSONL views from validated immutable events.
    - Require gate-ALLOW audit persistence before actuation.
    - Requirements: MCP-REQ-23, MCP-REQ-25
    - Design: §§9.2, 11
    - Dependencies: 2.3, 3.2
    - Validation:
      - Crash/fault injection never exposes partial events.
      - Event IDs are monotonic and required event ordering is preserved.
      - Audit failure before execute yields `AUDIT_FAILURE` and zero key sends.

- [ ] 6. Implement read and wait orchestration
  - Requirements: MCP-REQ-1, MCP-REQ-4–6, MCP-REQ-13–16, MCP-REQ-32
  - Design: §4.1; §§7.2–7.3
  - Dependencies: 4, 5.1, 5.2, 5.3

  - [ ] 6.1 Implement historical telemetry reads
    - Return accepted frames strictly after the exclusive cursor in ascending order with limit/truncation metadata.
    - Do not mutate Flight Watch cursor or lifecycle state.
    - Requirements: MCP-REQ-4, MCP-REQ-6
    - Property: MCP-P6
    - Dependencies: 4
    - Validation:
      - Generated histories verify ordering, bounds, empty pages, limit 1/500, and no side effects.

  - [ ] 6.2 Implement Flight Watch await
    - Start/renew the live session lease on first wait, await COMMAND or AUTH, atomically ingest lifecycle plus cursor, and return typed FRAME/TIMEOUT.
    - Ensure no `PostFileCreate` dependency or inbox polling exists in MCP runtime.
    - Requirements: MCP-REQ-1, MCP-REQ-5, MCP-REQ-13–16, MCP-REQ-32
    - Property: MCP-P6
    - Dependencies: 4, 5.1, 5.2, 5.3
    - Validation:
      - Arrival, silence, cancellation, overlapping wait, restart, COMMAND, AUTH, and epoch-change tests pass.
      - Static/config review finds no PostFileCreate telemetry hook and no MCP runtime file-watcher event bus.

- [ ] 7. Implement inspection and canonical planner
  - Requirements: MCP-REQ-7–10, MCP-REQ-12
  - Design: §§5.4, 6, 7.4–7.5
  - Dependencies: 2.4, 3.1, 4, 5.2

  - [ ] 7.1 Implement coherent AGC inspection context
    - Map daemon snapshot to typed MCP result and bind it to session, relevant delivered COMMAND, epoch, revision, capture time, and digest.
    - Invalidate context after five seconds, revision/epoch change, execution attempt, or session stop.
    - Requirements: MCP-REQ-7, MCP-REQ-8, MCP-REQ-17
    - Property: MCP-P5
    - Dependencies: 3.1, 4, 5.1
    - Validation:
      - Missing, stale, wrong-session, wrong-frame, changed-revision, changed-epoch, unavailable, KEY REL, and valid snapshots have expected results.

  - [ ] 7.2 Implement pure canonical planner
    - Load a validated injected catalog, select one supported command, perform integer conversions without clamping, expand exact keys/postcondition, and calculate canonical JSON SHA-256 digest.
    - Return catalog mismatch/unsupported/range errors without reserving execution.
    - Requirements: MCP-REQ-9, MCP-REQ-10, MCP-REQ-12
    - Property: MCP-P1
    - Dependencies: 2.4, 3.1, 7.1
    - Validation:
      - Approved V25/V34/V37 catalog examples pass.
      - Repeated plans are byte-for-byte stable.
      - Generated insert/delete/substitute/reorder key mutations never compare equal.

  - [ ] 7.3 Implement independent criticality policy
    - Classify V37/V34 while P40 and non-zero-delta-v P40 activation using current trusted AGC state.
    - Treat the frame critical bit only as audit metadata; it cannot lower computed criticality.
    - Requirements: MCP-REQ-12
    - Properties: P7, MCP-P1
    - Dependencies: 3.1, 7.2
    - Validation:
      - Cover P00/P40, misleading critical bit, and delta-v `-1`, `0`, `+1` boundary examples.
      - Contract equality test proves threshold remains zero across consumers.

- [ ] 8. Implement SafetyGate and execution coordinator
  - Requirements: MCP-REQ-8–25
  - Design: §§4.2–4.3, 5.2–5.4, 9–10
  - Dependencies: 5.2, 5.3, 7.1–7.3

  - [ ] 8.1 Implement fail-closed SafetyGate evaluation
    - Require fresh explicit inspection; obtain authoritative preflight; reload command; recompute plan/criticality; compare exact keys; check epoch, KEY REL, audit availability, command state, and AUTH.
    - Route every execute request through this component.
    - Requirements: MCP-REQ-8–13, MCP-REQ-17, MCP-REQ-25
    - Properties: P7, MCP-P1, MCP-P5
    - Dependencies: 5.2, 5.3, 7.1–7.3
    - Validation:
      - Instrumented adapter proves no execute path bypasses gate.
      - Every rejection code produces zero daemon key sends and unchanged AGC revision.

  - [ ] 8.2 Implement atomic claim and one-time AUTH consumption
    - Commit command `READY -> EXECUTING`, AUTH `MATCHED -> CONSUMED`, execution ID, and plan digest in one transaction before daemon actuation.
    - Close failed, expired, and unknown attempts without restoring AUTH.
    - Requirements: MCP-REQ-14–16, MCP-REQ-21–22
    - Properties: MCP-P2, MCP-P3
    - Dependencies: 8.1
    - Validation:
      - Fault injection at every transaction boundary yields either no claim/no actuation or one durable claim.
      - Concurrent attempts consume AUTH and claim the frame at most once.

  - [ ] 8.3 Implement idempotent daemon execution boundary
    - Add/complete daemon execution journal and one global DSKY writer lock.
    - Before every key check KEY REL, enforce at least 100 ms through injected timing, and after every key check OPR ERR.
    - Use frame sequence/plan digest/operation ID for idempotent daemon behavior.
    - Requirements: MCP-REQ-17, MCP-REQ-18, MCP-REQ-21, MCP-REQ-22
    - Properties: MCP-P3, MCP-P4
    - Dependencies: 2.2, 2.4, 8.2; external M3.8
    - Validation:
      - Fake-clock trace proves minimum cadence.
      - KEY REL and OPR ERR fault injection stops before the next key.
      - Concurrent different-frame traces contain no interleaving.

  - [ ] 8.4 Implement timeout reconciliation and postcondition verification
    - Distinguish pre-actuation timeout from possible-actuation disconnect; reconcile only through `execution.get(frame_seq)`.
    - Reinspect after reported completion and transition to EXECUTED only when postcondition matches and OPR ERR is clear.
    - Enter FAILED/HALTED for known failure or mismatch; preserve OUTCOME_UNKNOWN until reconciled.
    - Requirements: MCP-REQ-19, MCP-REQ-20, MCP-REQ-21, MCP-REQ-32
    - Property: MCP-P3
    - Dependencies: 8.3
    - Validation:
      - Disconnect tests at before-claim, after-claim/before-first-key, mid-sequence, and after-journal-commit points pass.
      - No path automatically resends the full sequence.
      - Matching/mismatching postcondition tests produce correct lifecycle and audit events.

- [ ] 9. Implement P7 and supporting property suites
  - Build a stateful Hypothesis rule machine with an independent safety model, fake clock, transactional ledger, instrumented daemon, restart/epoch rules, and concurrency schedules.
  - Cover arbitrary AGC states, supported commands, frame flags, key mutations, AUTH variants, deadlines, retries, audit failures, and daemon failures.
  - Add MCP-P1 through MCP-P7 tests at their owning boundaries.
  - Requirements: MCP-REQ-8–22, MCP-REQ-25, MCP-REQ-29
  - Design: §13 Correctness properties; §14.2
  - Dependencies: 8.1–8.4
  - Validation:
    - Quick profile runs approximately 100 examples/property through `python -m pytest -m "not slow"`.
    - Full P7 runs 10,000 generated cases through `python -m pytest`.
    - Stored report includes actual case count, seed, duration, command, output, and exit code.
    - On failure, preserve the exact Hypothesis counterexample; do not mark P7 passed.

- [ ] 10. Expose the six tools over MCP stdio
  - Register exactly the required tool names and strict schemas; connect them to services without embedding domain rules in the SDK adapter.
  - Return structured expected failures and translated internal failures.
  - Ensure stdio carries protocol data only; diagnostics go to the configured audit/log sink.
  - Requirements: MCP-REQ-1–11, MCP-REQ-20, MCP-REQ-25
  - Design: §§3.2, 7
  - Dependencies: 6.1, 6.2, 7.1–7.3, 8.1–8.4
  - Validation:
    - MCP discovery returns exactly six feature tools.
    - Each tool is called once through an actual stdio client fixture with valid and invalid input.
    - `verify_crc16` matches normative vectors and changes no cursor, ledger, audit decision, or AGC state.

- [ ] 11. Register MCP with least-privilege approval settings
  - Add local stdio server registration with explicit executable/arguments and no secrets in committed settings.
  - Do not auto-approve `execute_dsky_sequence` directly, by wildcard, or transitively.
  - If read-only tools are auto-approved, list each explicitly.
  - Requirements: MCP-REQ-2, MCP-REQ-24, MCP-REQ-31
  - Design: §12.4 MCP approval configuration
  - Dependencies: 10
  - Validation:
    - Parse effective MCP settings and assert execute is absent from every auto-approval expansion.
    - Start the registered server and call each tool from an MCP client.
    - Secret scan finds no operator/link key in settings or logs.

- [ ] 12. Create and verify Kiro hooks
  - Hooks are defense in depth and development automation; none may implement runtime telemetry delivery or replace SafetyGate.
  - Requirements: MCP-REQ-1, MCP-REQ-26–28
  - Design: §12 Hooks and MCP configuration
  - Dependencies: 1, 11

  - [ ] 12.1 Create `flight-mode-shell-guard` PreToolUse hook
    - Block shell/process and project-file mutation tool names with exit 2 only while a validated live Flight Watch lease exists.
    - Allow the six Apollo-26 MCP tools and fail closed for a stale/ambiguous marker until operator cleanup.
    - Requirements: MCP-REQ-26, MCP-REQ-32
    - Design: §12.1
    - Dependencies: 5.1, 11
    - Validation:
      - Fixtures cover marker absent, live, expired, malformed, wrong owner, and clean shutdown.
      - Live mode blocks shell and file mutation but allows all six MCP tools.
      - Review confirms the hook contains no AUTH or plan logic.

  - [ ] 12.2 Create `test-after-spec-task` PostTaskExec hook
    - Map completed task areas to focused checks and preserve output/exit code.
    - Report failed checks as failures; do not claim task validation passed.
    - Requirements: MCP-REQ-27
    - Design: §12.2
    - Dependencies: 1
    - Validation:
      - Simulated passing/failing task checks preserve the exact exit code and report path.
      - Hook timeout produces a visible failure, not a pass.

  - [ ] 12.3 Create `pbt-on-save` PostFileSave hook
    - Match Python under `mcp-server`, `agc-core`, and `acoustic`; skip while Flight Watch is live; debounce and prevent overlapping runs.
    - Run `python -m pytest -m "not slow"` and preserve evidence.
    - Requirements: MCP-REQ-28
    - Design: §12.3
    - Dependencies: 1, 5.1
    - Validation:
      - Matching/nonmatching paths, rapid repeated saves, active Flight Watch, pass, failure, and timeout fixtures behave as designed.
      - If the explicit TASK.md schedule cut defers this hook, record it as deferred rather than complete.

  - [ ] 12.4 Prove no PostFileCreate telemetry event bus exists
    - Review hook configuration and MCP runtime for file-create telemetry triggers or inbox file-watcher orchestration.
    - Requirements: MCP-REQ-1
    - Design: §§1, 4.1, 12
    - Dependencies: 12.1–12.3
    - Validation:
      - Automated configuration scan finds no `PostFileCreate` telemetry hook.
      - E2E Flight Watch receives a daemon frame through `await_telemetry_frame` with hooks disabled.

- [ ] 13. Run integration and end-to-end abuse suite
  - Requirements: MCP-REQ-1–25, MCP-REQ-30–32
  - Design: §14.3 Integration and E2E abuse tests
  - Dependencies: 9–12; external M2/M3 gates

  - [ ] 13.1 Validate normal Flight Watch flow
    - Exercise operator start, await, COMMAND delivery, inspect, plan, execute, post-inspect, and return to waiting through real stdio and loopback RPC boundaries.
    - Requirements: MCP-REQ-1–11, MCP-REQ-19
    - Dependencies: 10, 11, 12.4
    - Validation:
      - AGC postcondition matches and audit event chain is complete.
      - Latency is recorded as measured data; do not claim the target if it is not met.

  - [ ] 13.2 Validate frame-origin abuse paths
    - Exercise CRC failure, valid-CRC/HMAC failure, replay after daemon restart, noise/jamming, and sequence epoch reprovisioning.
    - Confirm rejected frames never appear as accepted MCP telemetry and never actuate.
    - Requirements: MCP-REQ-6, MCP-REQ-13, MCP-REQ-16, MCP-REQ-30
    - Dependencies: 13.1; external P4–P6
    - Validation:
      - Stable rejection codes occur at the owning daemon boundary.
      - Key-send trace remains empty for every rejected/noise case.

  - [ ] 13.3 Validate AUTH and canonical-plan abuse paths
    - Exercise critical P40 hold, wrong ref/provenance, AUTH-before-COMMAND, expiry boundaries, correct AUTH, reuse, misleading critical flag, and arbitrary plan mutation.
    - Requirements: MCP-REQ-8–16, MCP-REQ-29, MCP-REQ-30
    - Properties: P7, MCP-P1, MCP-P2
    - Dependencies: 9, 13.1
    - Validation:
      - Exactly one valid authorized attempt can reach daemon actuation.
      - Every other case produces the specified stable result and zero new keys.

  - [ ] 13.4 Validate execution failure and concurrency abuse paths
    - Exercise KEY REL before/mid-sequence, OPR ERR, duplicate/conflicting retries, same/different-frame races, RPC disconnect points, postcondition mismatch, cancellation, and restart reconciliation.
    - Requirements: MCP-REQ-17–22, MCP-REQ-25, MCP-REQ-30, MCP-REQ-32
    - Properties: MCP-P3, MCP-P4, MCP-P5, MCP-P7
    - Dependencies: 9, 13.1
    - Validation:
      - Traces show no key after stop condition, no interleaving, and no blind resend.
      - Lifecycle/audit records remain reconcilable after every injected crash point.

  - [ ] 13.5 Validate approval, hooks, boundaries, and evidence integrity
    - Review effective MCP approval configuration, hook behavior, import graph, local sockets, audit schema, and test report provenance.
    - Requirements: MCP-REQ-2, MCP-REQ-23–28, MCP-REQ-30–31
    - Dependencies: 11, 12, 13.1–13.4
    - Validation:
      - Execute is not auto-approved.
      - No reverse dependency or non-loopback command-path socket is observed.
      - UI/evidence inputs refer to generated reports, not hard-coded pass values.

- [ ] 14. Run final MCP bridge validation gate
  - Run focused schema, unit, P7, integration, restart, concurrency, hook, stdio, local-RPC, architecture, and abuse tests.
  - Repeat the required M4 E2E scenarios twice consecutively as required by `TASK.md`.
  - Update evidence only from stored outputs; leave unmet or unrun claims as `TARGET`, `UNMEASURED`, `PLANNED`, or `FAILED` as applicable.
  - Requirements: MCP-REQ-1–32
  - Design: §§13–15
  - Dependencies: 13.1–13.5
  - Validation:
    - `python -m pytest -m "not slow"` exits 0 and output/exit code are stored.
    - `python -m pytest` exits 0 and output/exit code are stored.
    - Full P7 report records the actual 10,000-case target outcome and seed.
    - MCP stdio/local-RPC E2E and all required abuse cases exit 0 twice consecutively.
    - Spec traceability review maps every MCP-REQ ID to design, task, and test evidence.
    - Do not mark this task complete if any required command is missing, unrun, or lacks preserved output/exit code.

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "2.1"] },
    { "wave": 2, "tasks": ["2.2", "2.3", "2.5", "3.1"] },
    { "wave": 3, "tasks": ["2.4", "3.2", "3.3"] },
    { "wave": 4, "tasks": ["4", "5.1", "5.2", "5.3"] },
    { "wave": 5, "tasks": ["6.1", "6.2", "7.1"] },
    { "wave": 6, "tasks": ["7.2"] },
    { "wave": 7, "tasks": ["7.3"] },
    { "wave": 8, "tasks": ["8.1"] },
    { "wave": 9, "tasks": ["8.2"] },
    { "wave": 10, "tasks": ["8.3"] },
    { "wave": 11, "tasks": ["8.4"] },
    { "wave": 12, "tasks": ["9"] },
    { "wave": 13, "tasks": ["10"] },
    { "wave": 14, "tasks": ["11"] },
    { "wave": 15, "tasks": ["12.1", "12.2", "12.3"] },
    { "wave": 16, "tasks": ["12.4"] },
    { "wave": 17, "tasks": ["13.1"] },
    { "wave": 18, "tasks": ["13.2", "13.3", "13.4"] },
    { "wave": 19, "tasks": ["13.5"] },
    { "wave": 20, "tasks": ["14"] }
  ]
}
```

```text
External M2.7 + M3.8
        |
1 ---- 2.1 ---- 2.2 -------- 4
|       |        |            |
|       +--2.3---+---- 5 -----+---- 6
|       |
|       +--2.4 ------ 7 ------+---- 8 ---- 9 ---- 10 ---- 11
|                                              |             |
+----------------------------------------------+---------- 12
                                                            |
                                         13.1 -> 13.2/13.3/13.4 -> 13.5 -> 14
```

`2.4` remains blocked until the AGC command catalog is verified. Contract/schema work, domain types, test infrastructure, and adapters can proceed in parallel where their listed dependencies permit.
