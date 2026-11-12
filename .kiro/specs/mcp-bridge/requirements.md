# Requirements Document

**Feature:** `mcp-bridge`  
**Workflow:** Design-First  
**Status:** Draft for review  
**Sources:** `PRD.md` §§5.2, 7, 9; `contracts/acoustic-frame-v1.md`; `docs/state-machines.md`; `docs/threat-model.md`; `docs/evidence-matrix.md`; `TASK.md` M4; active steering.

## Introduction

The MCP bridge connects a Kiro Flight Watch session to the acoustic daemon without moving safety decisions into the agent. It exposes six MCP tools over stdio, communicates with the daemon only through local RPC on `127.0.0.1`, produces canonical DSKY plans, and enforces authorization and execution safety in deterministic code.

The official runtime entry is: the operator starts Flight Watch, then the agent calls `await_telemetry_frame(timeout_sec)`. Kiro file hooks are development and defense-in-depth controls. `PostFileCreate` is not a telemetry event bus.

Each `MCP-REQ-n` heading contains one EARS acceptance criterion. The numeric alias `n.1` is used only by Kiro correctness-property metadata; the stable project ID remains `MCP-REQ-n`.

## Glossary

- **Accepted frame:** A `COMMAND` or `AUTH` already validated and published by the daemon according to the normative acoustic frame contract.
- **Flight Watch:** One operator-started MCP session that waits for accepted frames and coordinates inspect, plan, gate, execute, and verify.
- **Canonical plan:** The only ordered DSKY key sequence and postcondition permitted for a validated command under a specific command-catalog version.
- **Critical command:** A command that requires matching operator `AUTH`, regardless of the frame-provided `CRITICAL` flag.
- **Inspection context:** The most recent successful AGC snapshot for the current Flight Watch session, including daemon state revision and capture time.
- **Sequence epoch:** A daemon-issued identifier that changes only during explicit sequence reprovisioning and prevents pre-reset lifecycle records from becoming valid again.
- **Terminal command:** A command in `EXECUTED`, `FAILED`, or `EXPIRED` state.
- **Actuation attempt:** The atomic transition from an authorized/ready command to execution ownership. An attempt remains consumed even if execution fails or its outcome becomes unknown.

## Requirements

### Runtime and boundaries

#### MCP-REQ-1 — Official Flight Watch entry

**User story:** As an operator, I want Flight Watch to wait through MCP so that external daemon file creation is not mistaken for a Kiro hook event.

WHEN the operator starts Flight Watch, THE agent SHALL call `await_telemetry_frame(timeout_sec)` as the runtime entry and SHALL NOT depend on `PostFileCreate` or any filesystem hook to receive telemetry.

#### MCP-REQ-2 — Transport boundary

**User story:** As an operator, I want the bridge limited to local process boundaries so that the command path does not open a remote network interface.

THE MCP server SHALL use MCP stdio for agent communication and SHALL communicate with the acoustic daemon only through a schema-validated local RPC endpoint bound to `127.0.0.1`; it SHALL NOT bind or connect the daemon–MCP–AGC command path outside `127.0.0.1`.

#### MCP-REQ-3 — MCP tool surface

**User story:** As an agent developer, I want a small explicit tool surface so that read, plan, and write capabilities remain distinguishable.

WHEN a client performs MCP tool discovery, THE MCP server SHALL expose exactly these feature tools: `read_telemetry_frames`, `await_telemetry_frame`, `inspect_agc_status`, `plan_dsky_sequence`, `execute_dsky_sequence`, and `verify_crc16`.

#### MCP-REQ-4 — Historical telemetry reads

**User story:** As an investigator, I want bounded historical reads without changing Flight Watch progress.

WHEN `read_telemetry_frames(since_seq, limit)` receives valid input, THE MCP bridge SHALL return only daemon-accepted frames with `seq > since_seq`, in strictly increasing global sequence order, up to `limit`, and SHALL NOT advance the Flight Watch consumer cursor or alter command/AUTH lifecycle state.

#### MCP-REQ-5 — Await and timeout

**User story:** As a Flight Watch operator, I want bounded waiting with an explicit timeout so that silence does not look like a server failure.

WHEN `await_telemetry_frame(timeout_sec)` is called, THE MCP bridge SHALL return the next accepted `COMMAND` or `AUTH` after the session cursor exactly once and advance that cursor atomically; IF no frame arrives before the deadline, THEN it SHALL return a typed `TIMEOUT` result without advancing the cursor.

#### MCP-REQ-6 — Boundary validation

**User story:** As a maintainer, I want typed contracts at every process boundary so malformed or ambiguous data cannot enter trusted domain logic.

WHEN an MCP request, local RPC message, or persisted cross-process audit record crosses its trust boundary, THE receiving adapter SHALL validate it once against its versioned schema, reject unknown fields or unsupported schema versions, and convert it to typed domain values before invoking domain logic.

### Inspect, plan, and execute

#### MCP-REQ-7 — AGC inspection

**User story:** As the Flight Watch agent, I want a coherent AGC snapshot so planning is based on actual emulator state.

WHEN `inspect_agc_status()` succeeds, THE MCP bridge SHALL return a single-revision snapshot containing program, VERB, NOUN, R1–R3, DSKY input state, `KEY REL`, `OPR ERR`, other defined lamps, state revision, sequence epoch, and capture time.

#### MCP-REQ-8 — Inspect before plan and act

**User story:** As an operator, I want stale or missing inspections to fail closed.

IF `plan_dsky_sequence` or `execute_dsky_sequence` is requested without a successful inspection in the same Flight Watch session after the relevant `COMMAND` was delivered, OR the inspection is older than the catalog `inspection_max_age_ms` (20 seconds in catalog v1.0), OR its AGC revision/sequence epoch no longer matches current daemon state, THEN THE MCP bridge SHALL reject the request without sending a DSKY key.

#### MCP-REQ-9 — Deterministic canonical plan

**User story:** As an operator, I want one reproducible translation from command to keys so agent improvisation cannot change execution.

WHEN `plan_dsky_sequence(frame_seq)` receives an open accepted `COMMAND` and a fresh inspection context, THE MCP bridge SHALL deterministically return the canonical ordered keys, command-catalog version, plan digest, independently computed criticality, AUTH state, and expected AGC postcondition for that command and inspected revision.

#### MCP-REQ-10 — Canonical-plan enforcement

**User story:** As an operator, I want the write boundary to reject every noncanonical sequence.

WHEN `execute_dsky_sequence(keys, frame_seq)` is called, THE safety gate SHALL reload the accepted `COMMAND`, recompute the canonical plan and criticality from trusted state, and reject the call without actuation unless `keys` exactly equals the recomputed canonical key sequence.

#### MCP-REQ-11 — Mandatory safety gate

**User story:** As a safety reviewer, I want every write to pass deterministic policy regardless of agent behavior.

THE MCP bridge SHALL route every `execute_dsky_sequence` call through `mcp-server/safety_gate.py` before any daemon actuation request, regardless of prior tool results, agent claims, frame `CRITICAL` flag, or approval UI state.

### Critical commands and AUTH

#### MCP-REQ-12 — Critical classification

**User story:** As an operator, I want criticality computed from current AGC state and command meaning rather than trusted from untrusted metadata.

WHEN the safety gate evaluates a command, THE MCP bridge SHALL classify as critical: `V37` while P40 is active; `V34` while P40 is active; and activation of P40 when `abs(delta_v_tenths_fps) > 0`. The boundary value `delta_v_tenths_fps = 0` SHALL be noncritical unless another rule makes the command critical. The incoming `CRITICAL` flag SHALL NOT lower this classification.

#### MCP-REQ-13 — AUTH correlation and provenance

**User story:** As an operator, I want authorization tied to one specific command.

IF a critical command lacks an accepted `AUTH` validated by the daemon with the operator-key provenance and with `AUTH.ref_seq` equal to the `COMMAND.seq`, THEN THE safety gate SHALL return `AUTH_REQUIRED` or the applicable AUTH rejection and SHALL keep the command unexecuted.

#### MCP-REQ-14 — AUTH arrival and expiry

**User story:** As an operator, I want old or out-of-order authorization to fail closed.

WHEN an `AUTH` arrives before its referenced `COMMAND`, THE MCP bridge SHALL reject it with `STATE`; WHEN a critical `COMMAND` has remained `HELD` for the catalog `hold_expiry_ms` (120 seconds in catalog 1.2; originally 30 seconds) measured from the daemon acceptance timestamp, THE bridge SHALL atomically mark it `EXPIRED` and reject AUTH or execution at and after that deadline.

#### MCP-REQ-15 — One-time AUTH

**User story:** As an operator, I want one authorization to permit at most one execution attempt.

WHEN a matching valid AUTH authorizes a critical command, THE safety gate SHALL consume that AUTH atomically when execution ownership is claimed; after the command becomes `EXECUTING`, `EXECUTED`, `FAILED`, `EXPIRED`, or outcome-unknown, THE bridge SHALL reject all reuse of that AUTH and all additional actuation attempts for the command.

#### MCP-REQ-16 — Sequence restart and reprovisioning

**User story:** As a maintainer, I want restart and sequence reset behavior to preserve anti-replay and AUTH closure.

WHEN the daemon or MCP server restarts, THE MCP bridge SHALL reconcile its durable lifecycle ledger with the daemon sequence epoch and execution journal before allowing execution; IF the epoch changed during explicit reprovisioning, THEN it SHALL invalidate all pending COMMAND/AUTH and pre-reset inspection contexts before accepting new work.

### DSKY execution safety

#### MCP-REQ-17 — KEY REL enforcement

**User story:** As an operator, I want key release state checked at the actual actuation boundary.

IF `KEY REL` is active before execution or becomes active before any key, THEN the daemon execution boundary SHALL send no key while it remains active, SHALL stop the sequence, and SHALL return a typed failure that closes the actuation attempt.

#### MCP-REQ-18 — Key cadence and OPR ERR

**User story:** As an operator, I want key timing and input errors enforced below the agent layer.

WHILE a canonical sequence is executing, THE daemon execution boundary SHALL enforce at least 100 milliseconds between accepted key presses and SHALL inspect `OPR ERR` after each key; IF `OPR ERR` becomes active, THEN it SHALL stop before sending the next key and report the failed partial execution.

#### MCP-REQ-19 — Post-execution verification

**User story:** As an operator, I want success based on observed AGC state rather than successful transport alone.

WHEN daemon actuation reports completion, THE MCP bridge SHALL obtain a new AGC snapshot and compare it with the canonical postcondition; IF the postcondition matches and `OPR ERR` is clear, THEN it SHALL mark the command `EXECUTED`, otherwise it SHALL mark the command `FAILED`, enter the Flight Watch `HALTED` path, and require operator acknowledgement plus a safe state before further execution.

#### MCP-REQ-20 — Timeout and unknown outcome

**User story:** As an operator, I want timeouts to avoid unsafe blind retries.

WHEN a read-only RPC exceeds its deadline, THE MCP bridge SHALL return `TIMEOUT`; WHEN an execution RPC loses confirmation after actuation may have started, THE bridge SHALL return `OUTCOME_UNKNOWN`, SHALL reconcile by `frame_seq` with the daemon execution journal, and SHALL NOT automatically resend the full key sequence.

#### MCP-REQ-21 — Idempotent execution

**User story:** As an operator, I want retries to avoid duplicate key presses.

WHEN an identical execute request for a claimed or terminal `frame_seq` is repeated, THE MCP bridge SHALL return the stored/reconciled result without additional key actuation; IF the repeated request has a different key digest, THEN it SHALL reject it with `IDEMPOTENCY_CONFLICT` without actuation.

#### MCP-REQ-22 — Concurrent execution

**User story:** As an operator, I want concurrent requests serialized so DSKY sequences cannot interleave.

WHEN execute requests overlap, THE MCP bridge and daemon SHALL permit at most one atomic command claim per `frame_seq`, SHALL permit at most one active DSKY writer globally, and SHALL return `BUSY` or the idempotent prior result to losing requests without interleaving keys.

### Audit, errors, and approval

#### MCP-REQ-23 — Durable audit

**User story:** As an investigator, I want a complete record of each decision without exposing secrets.

WHEN the MCP bridge receives a tool call, changes COMMAND/AUTH state, makes a gate decision, starts or stops execution, reconciles an unknown outcome, or verifies a postcondition, THE bridge SHALL publish an immutable schema-valid audit event containing session/event IDs, timestamps from an injected clock, frame/reference sequence where applicable, plan/key digest, AGC revision, decision, stable error code, and resulting lifecycle state; it SHALL NOT record HMAC keys or environment secret values.

#### MCP-REQ-24 — No automatic approval for execute

**User story:** As an operator, I want the write tool to remain an explicit approval boundary.

THE Kiro MCP configuration SHALL NOT auto-approve `execute_dsky_sequence`, SHALL NOT include it through a wildcard auto-approval rule, and SHALL NOT let approval of any read-only tool imply approval of execution.

#### MCP-REQ-25 — Stable errors and fail-closed behavior

**User story:** As an integrator, I want stable machine codes and safe failure behavior.

IF validation, daemon availability, inspection freshness, planning, AUTH, audit persistence, concurrency, execution, or postcondition verification fails, THEN THE MCP bridge SHALL return the applicable stable error code defined by the design and SHALL perform no new actuation unless an execution attempt was already durably claimed and is being reconciled.

### Hooks and assurance

#### MCP-REQ-26 — Flight mode PreToolUse guard

**User story:** As an operator, I want an additional Kiro guard while Flight Watch is active.

WHILE the Flight Watch marker represents a live session, THE `PreToolUse` hook SHALL block shell and project-file mutation tools with exit code 2 and SHALL allow only the six Apollo-26 MCP tools needed by Flight Watch; the hook SHALL remain defense in depth and SHALL NOT replace the safety gate.

#### MCP-REQ-27 — PostTaskExec validation

**User story:** As a maintainer, I want completed spec tasks followed by relevant checks with reviewable evidence.

WHEN a `mcp-bridge` implementation task completes, THE `PostTaskExec` hook SHALL run the validation commands mapped to that task and preserve command, output, and exit code without marking a failed validation as passed.

#### MCP-REQ-28 — PostFileSave PBT profile

**User story:** As a maintainer, I want fast safety feedback after Python changes without spawning duplicate test storms.

WHEN a Python file under `mcp-server/`, `agc-core/`, or `acoustic/` is saved outside active Flight Watch, THE `PostFileSave` hook SHALL debounce concurrent saves and run the quick non-slow pytest profile; it SHALL preserve output and exit code and SHALL never fabricate a test result.

#### MCP-REQ-29 — P7 safety property

**User story:** As a safety reviewer, I want generated histories to demonstrate that critical commands cannot bypass AUTH.

FOR ALL supported commands, AGC states, agent-provided key sequences, AUTH lifecycle states, injected clock values, retry histories, and concurrent schedules, IF the command is critical and lacks one fresh matching unused AUTH, THEN the P7 property SHALL observe zero DSKY key actuation.

#### MCP-REQ-30 — End-to-end abuse coverage

**User story:** As a reviewer, I want the documented attack paths exercised through real boundaries.

WHEN the MCP bridge milestone is validated, THE E2E/abuse suite SHALL cover valid command execution; CRC rejection; valid-CRC/HMAC rejection; replay rejection across daemon restart; critical P40 hold, wrong AUTH, matching AUTH, and AUTH reuse; canonical mismatch; noise/jamming with zero wild keys; `KEY REL`; `OPR ERR`; duplicate and concurrent execute; expiry boundaries; RPC disconnect/unknown outcome; postcondition mismatch; and configuration review proving execute is not auto-approved.

#### MCP-REQ-31 — Ownership and injected dependencies

**User story:** As a maintainer, I want module boundaries preserved so safety logic remains testable without devices or ambient state.

THE MCP bridge SHALL keep frame validation and sequence persistence in `acoustic/`, AGC/DSKY state in `agc-core/`, orchestration and critical authorization in `mcp-server/`, and cross-process schemas in `contracts/`; clocks, filesystem stores, environment configuration, local RPC, and network endpoints SHALL enter library code only through explicit adapters.

#### MCP-REQ-32 — Flight Watch stop and cancellation

**User story:** As an operator, I want stopping Flight Watch to terminate waits without corrupting an in-flight command.

WHEN the operator stops Flight Watch or the stdio session closes, THE bridge SHALL cancel outstanding await operations, release the live-session marker, and preserve its durable cursor; IF execution was already claimed, THEN shutdown SHALL leave it in a reconcilable state and SHALL NOT cancel or retry actuation blindly.

## 4. Out of scope

- Acoustic demodulation, raw frame validation, HMAC secret loading, and global sequence persistence.
- AGC arithmetic and internal DSKY state-machine implementation.
- Mission Console presentation or browser-side safety enforcement.
- Additional MCP tools, remote MCP transport, AUTH-before-COMMAND buffering, sequence wraparound, or automatic recovery from partial DSKY execution.
- Treating hooks, prompts, the UI, or the frame `CRITICAL` bit as the normative authorization mechanism.
