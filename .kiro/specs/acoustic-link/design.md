# Acoustic Link Design

## Overview

This design keeps frame and modem logic pure, pushes microphone/filesystem/clock/network/environment access into adapters, and makes publication fail closed. It implements the 300-baud, 34-byte Apollo-26 v1 link without owning AGC state or critical-command authorization.

The channel spike in `TASK.md` task 1.2 has no stored measurements yet. SNR and frequency deviation therefore remain `UNMEASURED`; this design uses the contractual 48 kHz/44.1 kHz sample rates and leaves detection thresholds configurable through validated adapter input.

## 2. Decisions and trade-offs

| Decision | Chosen approach | Reason and rejected alternative |
| :-- | :-- | :-- |
| Receiver deadlines | 150 ms for sync; 1.25 s from sync to complete candidate | Two sync bytes need about 66.7 ms and the remaining body about 1.07 s at 300 baud. The margins fit the 2.0 s target. Unbounded waits were rejected because they permit jamming to pin state. |
| DSP structure | Pure batch/stream transforms driven by PCM chunks | Hardware calls inside modem code would make P2/P3/P5 nondeterministic and violate dependency rules. |
| Synchronization | Preamble qualification, falling-edge UART acquisition, center sampling, early/late correction | Fixed chunk alignment was rejected because callback boundaries are unrelated to symbol boundaries. |
| Stream storage | Preallocated 2-second ring plus bounded 32-block queue | Unbounded queues amplify random-audio denial of service. Dropping samples silently was rejected because it could splice a false candidate. |
| Acceptance commit | Stage inbox → commit sequence → promote inbox → publish | Committing inbox first violates the protocol. Committing sequence first without staging can consume a sequence with no recoverable inbox record after a crash. |
| Initial sequence | Explicitly provisioned state; missing state fails closed | Automatically recreating zero after deletion would reopen replay. |
| AUTH ownership | Acoustic layer validates wire/authenticity; safety gate validates pending, expiry, single-use, and critical policy | Duplicating authorization state in the daemon would conflict with `mcp-server/safety_gate.py` as source of truth. |
| Standalone anomaly transport | Typed in-process/diagnostic event until a contract schema exists | `websocket-events.schema.json` has no anomaly variant. Sending ad-hoc JSON would violate cross-process schema rules. |

## Architecture

```mermaid
flowchart LR
    MIC[MicrophoneAdapter] --> Q[Bounded AudioBlockQueue]
    WAV[WavAdapter] --> Q
    LOOP[LoopbackAdapter] --> Q
    Q --> RING[PCM RingBuffer]
    RING --> RX[StreamingReceiver]
    RX --> MODEM[GoertzelDemodulator]
    RX --> VALIDATE[FrameValidator]
    VALIDATE --> SEQ[SequenceStore port]
    VALIDATE --> RESULT[ValidationResult]
    RESULT --> TSTORE[TelemetryStore port]
    TSTORE --> PUB[Local Event Publisher]
    PUB --> WS[127.0.0.1 WebSocket adapter]
    DIAG[DiagnosticSink port] <-- RX
    DIAG <-- VALIDATE
```

Allowed dependency direction is adapters → application orchestration → pure domain/DSP. Pure modules depend only on NumPy where numerical arrays are required and on typed values from the acoustic package. They do not read environment, filesystem, devices, clock, or network.

## Components and Interfaces

Proposed modules:

| Module | Responsibility | Side effects |
| :-- | :-- | :-- |
| `acoustic/frame.py` | Typed frame values, encode/decode, CRC, HMAC input construction, ordered stateless checks | None |
| `acoustic/modem.py` | 8N1 serialization, phase-continuous modulation, Goertzel decisions, tone/deviation estimates | None |
| `acoustic/receiver.py` | IDLE/PREAMBLE/SYNC/RECEIVE state machine, timers via port, candidate assembly | None except returned events |
| `acoustic/ring_buffer.py` | Fixed-capacity mono PCM storage and overflow signal | None |
| `acoustic/validation.py` | Ordered validation orchestration with injected keys and sequence state | Calls sequence-store port only at final gate |
| `acoustic/sequence_store.py` | Port plus filesystem adapter for provision/load/atomic commit/recovery metadata | Filesystem adapter only |
| `acoustic/telemetry_store.py` | Schema validation, staging, atomic promotion, immutable rejected records | Filesystem adapter only |
| `acoustic/audio.py` | `AudioSource` protocol and microphone/WAV/loopback adapters | Boundary I/O only |
| `acoustic/daemon.py` | Composition root, bounded queue, status, recovery, local publisher | Explicit boundary orchestration |

The codec and modem do not import daemon, AGC, MCP, React, or audio-device modules. The daemon may later call `agc-core` and expose local RPC, but those integrations remain outside frame/modem logic.

## Data Models

Public APIs use type hints, `Enum`, immutable dataclasses, and validated values rather than free-form dictionaries.

```python
class FrameType(Enum):
    COMMAND = 0x01
    AUTH = 0x02

class RejectReason(Enum):
    LENGTH = "LENGTH"
    SYNC = "SYNC"
    VERSION = "VERSION"
    TYPE = "TYPE"
    CRC = "CRC"
    FLAGS = "FLAGS"
    HMAC = "HMAC"
    REPLAY = "REPLAY"
    RANGE = "RANGE"
    STATE = "STATE"
    INTERNAL = "INTERNAL"

@dataclass(frozen=True)
class CommandFrame: ...

@dataclass(frozen=True)
class AuthFrame: ...

@dataclass(frozen=True)
class ValidationResult:
    verdict: Literal["ACCEPTED", "REJECTED"]
    reason: RejectReason | None
    frame: CommandFrame | AuthFrame | None
    checks: ValidationChecks

class AudioSource(Protocol):
    @property
    def metadata(self) -> SourceMetadata: ...
    def blocks(self) -> Iterator[AudioBlock]: ...

class SequenceStore(Protocol):
    def load(self) -> SequenceState: ...
    def commit(self, next_seq: int) -> None: ...

class TelemetryStore(Protocol):
    def stage_accepted(self, record: TelemetryRecord) -> StagedRecord: ...
    def promote(self, staged: StagedRecord) -> FinalRecord: ...
    def write_rejected(self, record: TelemetryRecord) -> FinalRecord: ...
```

`KeyMaterial` is injected by the composition root after environment validation and is never serialized or logged. `Clock`, `EventIdSource`, `DiagnosticSink`, and network listeners are also injected ports.

## 5. Frame codec and validation

### 5.1 Pure encoding

The encoder assembles a fixed 34-byte buffer. It writes sync, version, type, integer fields in big-endian order, then computes the first eight HMAC-SHA256 bytes over offsets 2–23, then CRC-16/CCITT-FALSE over offsets 2–31. Signed values use two's-complement fixed-width conversion; no floating-point conversion occurs in the codec.

### 5.2 Ordered decode and validation

Validation returns the first stable reason and marks later checks `null` in the telemetry representation when they were not run:

1. Check exact length.
2. Check `A5 26`.
3. Check version 1 and type 1/2.
4. Check CRC over bytes 2–31.
5. Check reserved flags and stateless type semantics.
6. Select link/operator key from the decoded type and compare HMAC with `hmac.compare_digest` or an equivalent standard constant-time primitive.
7. Compare sequence against injected persisted state.
8. Check ranges and remaining acoustic-domain rules.
9. Stage accepted telemetry and call atomic sequence commit through orchestration.

`COMMAND.ref_seq=0`. `AUTH.ref_seq` is nonzero and all payload/flag fields are zero. The acoustic layer does not decide whether that reference is pending or usable. The safety gate later recomputes criticality and enforces AUTH matching, 30-second expiry, and one-time use.

## 6. Modulator

### 6.1 Serialization

The serializer emits 75 mark symbols for the minimum 250 ms preamble at 300 baud, followed by each byte as `0`, eight LSB-first data bits, `1`. A valid 34-byte body contains 340 symbols and lasts about 1.133 seconds. The minimum complete waveform therefore lasts about 1.383 seconds.

### 6.2 Continuous phase

For each output sample:

```text
sample[n] = amplitude × sin(phase[n])
phase[n+1] = (phase[n] + 2π × frequency(bit[n]) / sample_rate) mod 2π
```

The phase accumulator is initialized once per burst and never reset at symbol or byte boundaries. Supported rates divide exactly by 300: 160 samples/symbol at 48 kHz and 147 at 44.1 kHz. Output is mono float PCM with explicit clipping protection at the adapter boundary.

## 7. Goertzel demodulator and synchronization

### 7.1 Tone decision

The demodulator computes Goertzel energy at 1200 and 2200 Hz over one-symbol windows. During acquisition, windows advance by one quarter symbol to avoid callback/alignment dependence. A decision requires both minimum energy and a configurable mark-to-space confidence ratio. Thresholds are validated configuration supplied by the composition root; measurements from spike 1.2 must replace tuning assumptions when available.

### 7.2 Preamble and UART synchronization

1. Accumulate qualified overlapping mark windows until duration is at least 250 ms.
2. Detect the mark-to-space falling edge expected for the first UART start bit.
3. Evaluate candidate sampling phases around the edge and select the phase with the highest aggregate tone confidence that also satisfies start=`0` and stop=`1`.
4. Decode the first two 8N1 bytes and require `A5 26` within the 150 ms sync deadline.
5. Sample later symbols at their centers. Apply bounded early/late timing correction of at most one eighth symbol per byte; never insert or delete data silently.
6. Abort on invalid UART framing or the 1.25-second receive deadline.

The receiver freezes exactly 34 bytes. It never grows a buffer while searching for an end delimiter.

### 7.3 Frequency deviation

A complex correlation/phase-slope estimator runs only on tone runs with enough confidence and duration to resolve the strict 50 Hz boundary. For each candidate it retains the maximum absolute qualified deviation from the expected mark or space. A deviation above 50 Hz emits `FrequencyAnomaly`; exactly 50 Hz does not. Insufficient-confidence estimates do not invent a value and do not independently change the frame verdict.

## 8. Ring buffer and concurrency

The audio callback performs bounded work: validate block shape, copy mono PCM into a preallocated 2-second ring, and enqueue a descriptor. It performs no decoding, file I/O, schema validation, or network operation.

The processing queue holds at most 32 blocks, each at most 20 ms. One worker owns receiver state and sequence acceptance, so two candidates cannot commit the same sequence concurrently. Overflow invalidates the current candidate, emits one `INTERNAL` incident, clears acquisition state, and requires a fresh preamble. This prevents samples on opposite sides of a drop from being joined.

At 48 kHz, the ring contains at most 96,000 float32 samples (384,000 bytes); at 44.1 kHz it contains at most 88,200 samples (352,800 bytes), excluding small fixed metadata.

## 9. Input adapters

- **MicrophoneAdapter:** prefers 48 kHz and falls back to 44.1 kHz only when device capabilities require it. Device enumeration and selection occur at the boundary.
- **WavAdapter:** accepts validated mono PCM at a supported sample rate. Conversion policy, if later allowed, must be explicit; v1 rejects unsupported rate/encoding. EOF drains queued samples and produces deterministic exit status.
- **LoopbackAdapter:** emits PCM blocks with `source.kind=loopback` through the same `AudioSource` protocol.

Adapters normalize chunk shape but do not demodulate or validate frames. Equivalent PCM therefore enters the same ring, receiver, validator, sequence store, and telemetry store.

## 10. Sequence persistence and crash recovery

### 10.1 State

The sequence file has a versioned typed representation with `schema_version` and `last_accepted_seq`. The daemon never creates a zero state implicitly. A separate explicit provisioning action creates or replaces it with restrictive local permissions and requires downstream pending COMMAND/AUTH state to be cleared.

Missing, malformed, unreadable, unsupported, or out-of-range state prevents the audio source from opening and reports `DEGRADED`. Value `0xFFFFFFFF` also locks the link until explicit reprovisioning.

### 10.2 Atomic commit protocol

For accepted sequence `N`:

1. Build and schema-validate the full telemetry record.
2. Write it to a same-directory staged file in `telemetry/inbox/`; flush and close.
3. Write the new sequence state to a same-directory temporary file; flush and close.
4. Atomically replace the sequence state file.
5. Atomically rename staged telemetry to `telemetry/inbox/N.json`.
6. Emit the schema-valid local WebSocket event.

Consumers ignore temporary/staged names. On restart, recovery runs before audio opens. A valid staged record matching persisted `N`, with no final `N.json`, is promoted once. Any inconsistent stage causes fail-closed `DEGRADED`. This closes the sequence/inbox crash gap while preserving the normative rule that sequence commit precedes publication.

Rejected records use unique immutable final names and same-directory temporary files. Final inbox and rejected files form an append-only audit collection; the daemon does not mutate or delete them.

## Error Handling

Errors are split so transport failures cannot masquerade as frame verdicts:

| Category | Typed examples | Handling |
| :-- | :-- | :-- |
| Frame rejection | Contract `RejectReason` values | Atomic rejected telemetry; daemon continues unless persistence state is unsafe |
| Source | `SOURCE_CONFIG`, `SOURCE_UNAVAILABLE`, `SOURCE_IO` | Diagnostic/status event; no fabricated frame reason; recoverable device I/O retries at most once/second |
| Persistence | `SEQUENCE_LOAD`, `SEQUENCE_COMMIT`, `INBOX_PROMOTE`, `AUDIT_WRITE_FAILED`, `RECOVERY_CONFLICT` | Sequence/accepted-path failures are fail-closed; rejected-audit failure is diagnosed while listener remains alive |
| Network | `NON_LOOPBACK_BIND`, `LISTENER_START` | Reject startup before unsafe bind |
| Configuration | invalid sample rate, baud, thresholds, paths | Validate once at composition boundary and do not start affected adapter |

Code does not catch bare `Exception` without adding operation, source, candidate ID, and causal context or translating it to one of these domain errors. Secrets and HMAC keys are never included in context.

## 12. Local publication and network boundary

HTTP, WebSocket, and later local RPC adapters bind an explicit `127.0.0.1`. The configuration type accepts no alternative address. The acoustic daemon has no outbound network adapter. Browser delivery and console events may use loopback listeners; MCP transport remains stdio and later daemon RPC remains loopback.

Accepted and rejected telemetry events must validate against existing contracts. The current WebSocket schema has no standalone frequency-anomaly event. Until that contract changes in a separately authorized task, anomalies remain typed internal/diagnostic events and candidate deviation remains available through `telemetry-frame.schema.json`.

## 13. Observability

Every event receives an injected monotonic event ID and injected wall-clock timestamp. Logs include source, state transition, candidate ID, sequence when decoded, first reason, persistence operation, and measured deviation. They exclude key material and do not label frequency drift as CRC failure.

Evidence labels follow `docs/evidence-matrix.md`: current latency, reliability, SNR, RAM, CPU, network isolation, and PBT counts are `UNMEASURED` or `TARGET` until reports retain command, exit code, duration, seed/environment, and result.

## 14. Performance budget

| Item | Budget/target | Design control |
| :-- | :-- | :-- |
| Physical burst | ~1.383 s minimum | Fixed 250 ms preamble + 340 body symbols |
| Deterministic path | TARGET ≤2.0 s first sample → final inbox | 150 ms sync bound, 1.25 s post-sync receive bound, no I/O in audio callback |
| Ring memory | ≤384,000 PCM bytes at 48 kHz | Preallocated 2-second float32 ring |
| Work queue | ≤32 × 20 ms blocks | Bounded descriptors, overflow abort |
| Candidate | 34 bytes | Fixed buffer |
| Room decode | TARGET ≥19/20 at 0.5 m | Controlled trial; actual result retained |
| Process memory | TARGET ≤256 MB | Bounded buffers and queues |
| Idle CPU | TARGET ≤10% | Goertzel windows and acquisition hop; measure on development laptop |
| Network | TARGET 0 sockets outside `127.0.0.1` | Explicit loopback-only adapters and process inspection |

The design does not claim these targets are met.

## Testing Strategy

Testing uses pure unit tests for codec/DSP, Hypothesis for P1–P6, fault-injection tests for persistence and restart boundaries, schema tests for every cross-process payload, process-level network inspection, and controlled measurements for latency, room reliability, memory, and CPU. Full-profile reports retain commands, exit codes, durations, seeds, environments, and counterexamples.

## Correctness Properties

The following properties define finite generated evidence rather than mathematical proof.

### Property 1: P1 Frame byte round-trip

For every valid typed COMMAND/AUTH, decoding its encoded 34 bytes returns the same domain values and canonical bytes.

**Validates: Requirements 3.1, 3.2, 4.1, 4.2**

- **Apollo IDs:** AL-REQ-3.1, AL-REQ-3.2, AL-REQ-4.1, AL-REQ-4.2
- **Evidence:** `tests/test_frame.py`, 10,000 examples and shared vectors

### Property 2: P2 Clean audio round-trip

For every valid frame and supported sample rate, demodulating its clean modulated waveform returns the identical 34 bytes and accepted frame.

**Validates: Requirements 1.2, 1.3, 2.2, 2.8, 3.1**

- **Apollo IDs:** AL-REQ-1.2, AL-REQ-1.3, AL-REQ-2.2, AL-REQ-2.8, AL-REQ-3.1
- **Evidence:** `tests/test_modem.py`, 500 examples

### Property 3: P3 Noisy audio round-trip

For every generated valid frame under the documented additive-white-noise method at SNR at least 15 dB, the modem returns the identical frame when the waveform is not clipped.

**Validates: Requirements 1.2, 2.8, 10.3, 10.4**

- **Apollo IDs:** AL-REQ-1.2, AL-REQ-2.8, AL-REQ-10.3, AL-REQ-10.4
- **Evidence:** `tests/test_modem.py`, 300 examples with seed and SNR retained

### Property 4: P4 Bit corruption rejection

For every tested single- or double-bit mutation of a valid frame without recomputing integrity fields, validation rejects before persistence or publication.

**Validates: Requirements 3.3, 3.4, 5.3, 5.4, 8.3**

- **Apollo IDs:** AL-REQ-3.3, AL-REQ-3.4, AL-REQ-5.3, AL-REQ-5.4, AL-REQ-8.3
- **Evidence:** `tests/test_frame.py`, 10,000 examples

### Property 5: P5 Random audio safety

For generated noise, unrelated tones, clicks, arbitrary chunking, and bounded overload, the acoustic pipeline emits no accepted frame and remains bounded and recoverable. A later cross-module integration test verifies no DSKY actuation.

**Validates: Requirements 2.9, 7.1, 7.2, 7.3, 10.4**

- **Apollo IDs:** AL-REQ-2.9, AL-REQ-7.1, AL-REQ-7.2, AL-REQ-7.3, AL-REQ-10.4
- **Evidence:** `tests/test_modem.py`, 1,000 examples and a load test

### Property 6: P6 Authentication and replay rejection

For any frame with wrong HMAC and valid recomputed CRC, or any sequence not greater than persisted state including after restart, validation rejects without publication.

**Validates: Requirements 4.1, 4.2, 5.4, 5.5, 9.4**

- **Apollo IDs:** AL-REQ-4.1, AL-REQ-4.2, AL-REQ-5.4, AL-REQ-5.5, AL-REQ-9.4
- **Evidence:** `tests/test_frame.py`, 10,000 examples and restart integration

Additional example and edge tests cover exact 50 Hz versus greater than 50 Hz, 150 ms/1.25 s deadline boundaries, each atomic-write failure point, missing/corrupt sequence state, staged-record recovery, maximum sequence exhaustion, source disconnect/recovery, and non-loopback bind rejection.

## 16. Requirement coverage

| Requirement | Design sections |
| :-- | :-- |
| AL-REQ-1 | 6 |
| AL-REQ-2 | 7, 8 |
| AL-REQ-3 | 4, 5 |
| AL-REQ-4 | 5 |
| AL-REQ-5 | 5, 10, 11 |
| AL-REQ-6 | 9 |
| AL-REQ-7 | 8, 9 |
| AL-REQ-8 | 10, 12 |
| AL-REQ-9 | 10 |
| AL-REQ-10 | 7.3, 12, 13 |
| AL-REQ-11 | 12 |
| AL-REQ-12 | 13 |
| AL-REQ-13 | 14, 15 |
