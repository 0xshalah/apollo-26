# Requirements Document

## Introduction

Feature ini menerima atau menghasilkan burst Bell-202 Apollo-26, memvalidasi frame wire v1, mempertahankan anti-replay setelah restart, dan menerbitkan telemetry yang tervalidasi kepada konsumen lokal. Scope meliputi `acoustic/` dan kontraknya dengan filesystem serta server localhost. Keputusan DSKY, lifecycle otorisasi kritis, dan enforcement safety gate tetap milik spec `mcp-bridge`.

Sumber normatif wire format adalah `contracts/acoustic-frame-v1.md`. JSON lintas proses wajib sesuai `contracts/telemetry-frame.schema.json` atau `contracts/websocket-events.schema.json`.

## Glossary

- **Candidate**: tepat 34 byte yang dibekukan receiver untuk validasi.
- **Accepted**: candidate yang melewati seluruh validasi dan whose sequence sudah tersimpan atomik.
- **Published**: accepted record sudah memiliki file final di inbox dan boleh dikirim ke konsumen.
- **Operational event**: event internal typed untuk status/anomali; event ini tidak boleh dikirim lintas proses sebelum memiliki JSON Schema kontrak.
- **Explicit provisioning**: tindakan operator di luar UI biasa untuk membuat atau mereset sequence store.

## Requirements

### AL-REQ-1 — Physical encoding at 300 baud

**User story:** Sebagai operator, saya ingin satu encoding fisik yang deterministik agar transmitter dan receiver tidak bernegosiasi mode yang ambigu.

Acceptance criteria:

1. **AL-REQ-1.1:** THE acoustic link SHALL support exactly 300 symbols per second in v1 and SHALL reject any configured baud rate other than 300 before processing audio.
2. **AL-REQ-1.2:** WHEN the modulator emits a data bit, THE modulator SHALL represent `1` as 1200 Hz mark and `0` as 2200 Hz space while preserving oscillator phase across every bit and byte boundary.
3. **AL-REQ-1.3:** WHEN the modulator serializes a frame, THE modulator SHALL emit at least 250 ms of continuous mark followed by exactly 34 bytes in 8N1 form: one start bit `0`, eight data bits least-significant-bit first, and one stop bit `1`.
4. **AL-REQ-1.4:** WHILE a 34-byte frame body is being emitted, THE modulator SHALL introduce no inter-byte or inter-frame gap inside that body.
5. **AL-REQ-1.5:** WHERE the sample rate is 48,000 Hz or 44,100 Hz, THE modulator SHALL emit exactly 160 or 147 samples per symbol respectively.

### AL-REQ-2 — Receiver acquisition, synchronization, and timeout

**User story:** Sebagai operator, saya ingin receiver kembali ke kondisi siap setelah sinyal parsial agar noise atau jamming tidak menggantung daemon.

Acceptance criteria:

1. **AL-REQ-2.1:** WHEN mark energy first exceeds the configured detection threshold, THE receiver SHALL enter `PREAMBLE`, set `UPLINK ACTY`, and start a preamble timer using an injected monotonic clock.
2. **AL-REQ-2.2:** WHEN mark remains qualified for at least 250 ms, THE receiver SHALL enter `SYNC` and search for the 8N1 encoding of sync bytes `A5 26`.
3. **AL-REQ-2.3:** IF qualified mark is lost before 250 ms, THEN THE receiver SHALL discard the partial candidate, clear `UPLINK ACTY`, and return to `IDLE` without publishing a frame.
4. **AL-REQ-2.4:** IF `A5 26` is not acquired within 150 ms after entering `SYNC`, THEN THE receiver SHALL record `SYNC`, clear the candidate, clear `UPLINK ACTY`, and return to `IDLE`.
5. **AL-REQ-2.5:** WHEN sync is acquired, THE receiver SHALL start a fixed 34-byte candidate buffer and SHALL include `A5 26` as bytes 0–1.
6. **AL-REQ-2.6:** IF a complete candidate is not available within 1.25 seconds after sync acquisition, THEN THE receiver SHALL reject the partial candidate as `LENGTH`, clear `UPLINK ACTY`, and return to `IDLE`.
7. **AL-REQ-2.7:** IF an 8N1 start or stop bit is invalid, THEN THE receiver SHALL reject the partial candidate as `LENGTH`, clear `UPLINK ACTY`, and return to `IDLE`.
8. **AL-REQ-2.8:** WHEN exactly 34 bytes have been received, THE receiver SHALL freeze the candidate, invoke validation once, and accept no further samples into that candidate.
9. **AL-REQ-2.9:** WHEN any acquisition, framing, or validation attempt ends, THE daemon SHALL remain running and the receiver SHALL become able to detect the next preamble.

### AL-REQ-3 — Pure 34-byte frame codec

**User story:** Sebagai pengembang, saya ingin codec murni agar wire format dapat diuji tanpa audio, filesystem, network, clock, atau environment.

Acceptance criteria:

1. **AL-REQ-3.1:** WHEN a valid typed frame is encoded, THE codec SHALL produce exactly 34 bytes with the offsets, widths, constants, and big-endian encodings in `contracts/acoustic-frame-v1.md`.
2. **AL-REQ-3.2:** WHEN a valid 34-byte frame is decoded, THE codec SHALL return typed `COMMAND` or `AUTH` domain values without reading environment, filesystem, microphone, clock, or network.
3. **AL-REQ-3.3:** WHEN CRC is generated or checked, THE codec SHALL use CRC-16/CCITT-FALSE with polynomial `0x1021`, initial value `0xFFFF`, no reflection, xorout `0x0000`, and coverage over bytes 2–31.
4. **AL-REQ-3.4:** WHEN HMAC is generated or checked, THE codec SHALL use the first 8 bytes of HMAC-SHA256 over bytes 2–23 and SHALL exclude sync, HMAC, and CRC from HMAC input.
5. **AL-REQ-3.5:** WHEN codec behavior is tested, THE Python codec SHALL consume `contracts/vectors/frames.json` directly and SHALL match every expected byte string and verdict; vector status SHALL remain unverified until both Python and TypeScript checks exist.
6. **AL-REQ-3.6:** IF input length is not exactly 34 bytes, THEN THE codec SHALL return `LENGTH` without indexing unavailable fields.

### AL-REQ-4 — COMMAND and AUTH wire semantics

**User story:** Sebagai safety-gate consumer, saya ingin tipe frame dan kunci dipisahkan agar COMMAND tidak dapat menyamar sebagai AUTH.

Acceptance criteria:

1. **AL-REQ-4.1:** WHEN a `COMMAND` is validated, THE validator SHALL require `frame_type=01`, `ref_seq=0`, and HMAC verification with injected link-key bytes.
2. **AL-REQ-4.2:** WHEN an `AUTH` is validated, THE validator SHALL require `frame_type=02`, nonzero `ref_seq`, zero `flags`, `verb`, `noun`, `program`, `r1`, `r2`, and `delta_v`, and HMAC verification with injected operator-key bytes.
3. **AL-REQ-4.3:** IF reserved flag bits 1–7 are nonzero or per-type field constraints fail, THEN THE validator SHALL reject the frame as `FLAGS` before checking HMAC.
4. **AL-REQ-4.4:** WHEN the daemon publishes a valid `AUTH`, THE daemon SHALL preserve `seq` and `ref_seq` but SHALL NOT itself mark a critical command authorized or executable.
5. **AL-REQ-4.5:** WHILE no `mcp-bridge` critical threshold has been approved, THE acoustic link SHALL preserve all COMMAND fields and SHALL leave P40 critical classification and AUTH one-time/expiry enforcement to `mcp-server/safety_gate.py`, where all P40 activation is fail-closed as critical.

### AL-REQ-5 — Ordered validation, integrity, authentication, and replay defense

**User story:** Sebagai operator, saya ingin setiap invalid frame berhenti pada reason pertama agar hasil audit deterministik dan tidak ada frame invalid yang diterbitkan.

Acceptance criteria:

1. **AL-REQ-5.1:** WHEN a candidate is validated, THE validator SHALL stop at the first failure in this order: exact length; sync; known version/type; CRC; flags and stateless per-type semantics; HMAC; replay; field range/domain; atomic sequence persistence.
2. **AL-REQ-5.2:** WHEN HMAC values are compared, THE validator SHALL use a standard constant-time comparison primitive.
3. **AL-REQ-5.3:** IF CRC does not match, THEN THE validator SHALL return `CRC` and SHALL NOT perform HMAC, replay, persistence, inbox publication, or WebSocket publication.
4. **AL-REQ-5.4:** IF HMAC does not match after a valid CRC, THEN THE validator SHALL return `HMAC` and SHALL NOT persist or publish the frame.
5. **AL-REQ-5.5:** IF `seq=0` or `seq <= last_accepted_seq`, THEN THE validator SHALL return `REPLAY` and SHALL NOT persist or publish the frame.
6. **AL-REQ-5.6:** WHEN either a `COMMAND` or `AUTH` is accepted, THE daemon SHALL update one shared global `last_accepted_seq` domain.
7. **AL-REQ-5.7:** IF field values fall outside their wire ranges or a remaining domain rule fails, THEN THE validator SHALL return `RANGE` and SHALL NOT persist or publish the frame.
8. **AL-REQ-5.8:** WHEN a frame is rejected, THE daemon SHALL create an immutable rejected audit record with the first stable reason code and SHALL continue listening.

### AL-REQ-6 — Microphone, WAV, and loopback adapters

**User story:** Sebagai demonstrator, saya ingin sumber live dan deterministik menggunakan pipeline yang sama agar fallback WAV tidak mengubah validasi.

Acceptance criteria:

1. **AL-REQ-6.1:** WHERE no alternate input is selected, THE daemon SHALL use the microphone adapter and SHALL prefer 48,000 Hz with a documented 44,100 Hz fallback.
2. **AL-REQ-6.2:** WHERE `--input <file.wav>` is selected, THE daemon SHALL validate PCM format at the adapter boundary, feed PCM through the same receiver and validator used by microphone input, drain pending samples at EOF, and then terminate with a deterministic success or domain error status.
3. **AL-REQ-6.3:** WHERE `--loopback` is selected, THE daemon SHALL feed loopback PCM through the same receiver and validator used by microphone input.
4. **AL-REQ-6.4:** WHEN equivalent PCM chunks and source metadata are supplied by microphone, WAV, or loopback adapters, THE receiver SHALL produce equivalent frame verdicts; only `source.kind` may differ.
5. **AL-REQ-6.5:** IF an input requests a sample rate other than 48,000 or 44,100 Hz, THEN THE adapter SHALL reject it before receiver processing with a typed source-configuration error.
6. **AL-REQ-6.6:** IF the selected audio device is unavailable at startup, THEN THE daemon SHALL report `SOURCE_UNAVAILABLE`, set audio status to `DEGRADED`, publish no frame, and remain controllably stoppable.

### AL-REQ-7 — Bounded streaming and source recovery

**User story:** Sebagai operator, saya ingin memory dan work queue tetap terbatas saat menerima noise atau ketika consumer melambat.

Acceptance criteria:

1. **AL-REQ-7.1:** WHILE streaming at either supported sample rate, THE receiver SHALL retain no more than 2.0 seconds of mono PCM in its ring buffer.
2. **AL-REQ-7.2:** WHILE audio callbacks enqueue work, THE daemon SHALL bound the processing queue to at most 32 blocks of at most 20 ms each and SHALL allocate no candidate buffer larger than 34 bytes.
3. **AL-REQ-7.3:** IF ring-buffer or processing-queue capacity is exceeded, THEN THE receiver SHALL abort the current candidate as `INTERNAL`, emit one operational overflow event for that incident, return to `IDLE`, and remain running without accepting bytes assembled across the dropped region.
4. **AL-REQ-7.4:** IF a running microphone or loopback source reports a recoverable I/O failure, THEN THE daemon SHALL discard partial receiver state, mark audio `DEGRADED`, and retry through the adapter no more often than once per second using an injected clock.
5. **AL-REQ-7.5:** WHEN a failed source becomes available, THE daemon SHALL create a fresh receiver session, mark audio `READY`, and require a new full preamble before accepting data.

### AL-REQ-8 — Atomic telemetry and publication order

**User story:** Sebagai Flight Watch consumer, saya ingin hanya melihat file lengkap yang sequence-nya sudah committed.

Acceptance criteria:

1. **AL-REQ-8.1:** WHEN any accepted or rejected frame record crosses a process boundary, THE daemon SHALL validate it against `contracts/telemetry-frame.schema.json` before writing or sending it.
2. **AL-REQ-8.2:** WHEN telemetry is written, THE telemetry store SHALL write a same-directory temporary file, flush and close it, and atomically replace or rename it to a unique final name; consumers SHALL ignore temporary names.
3. **AL-REQ-8.3:** WHEN a candidate is accepted, THE daemon SHALL stage the complete inbox JSON, atomically persist its sequence, atomically promote the staged JSON to `telemetry/inbox/<seq>.json`, and only then publish the WebSocket event in that order.
4. **AL-REQ-8.4:** IF sequence persistence fails, THEN THE daemon SHALL return `INTERNAL`, SHALL NOT promote or publish the accepted record, SHALL enter sequence status `DEGRADED`, and SHALL reject subsequent candidates fail-closed until recovery.
5. **AL-REQ-8.5:** IF final inbox promotion fails after sequence persistence, THEN THE daemon SHALL retain a recoverable staged record, publish nothing, report `INTERNAL`, and recover that record on restart before processing new audio.
6. **AL-REQ-8.6:** WHEN a frame is rejected, THE daemon SHALL atomically write one immutable record under `telemetry/rejected/` and SHALL never overwrite a previous audit record.
7. **AL-REQ-8.7:** IF a rejected-audit write fails, THEN THE daemon SHALL emit a structured operational `AUDIT_WRITE_FAILED` message to the configured diagnostic sink, publish no frame, and remain running.
8. **AL-REQ-8.8:** WHILE the daemon owns telemetry storage, THE daemon SHALL treat the collection of immutable inbox and rejected event files as an append-only session audit and SHALL not edit or delete finalized records.

### AL-REQ-9 — Sequence store, restart, and exhaustion

**User story:** Sebagai operator, saya ingin restart atau state corruption tidak membuka replay window.

Acceptance criteria:

1. **AL-REQ-9.1:** WHEN the daemon starts, THE sequence store SHALL load one explicitly provisioned global `last_accepted_seq` before accepting audio.
2. **AL-REQ-9.2:** IF sequence state is missing, malformed, out of range, unreadable, or has an unsupported schema version, THEN THE daemon SHALL enter `DEGRADED`, accept and publish no frame, and require explicit operator provisioning or recovery.
3. **AL-REQ-9.3:** WHEN `last_accepted_seq` changes, THE sequence store SHALL write a same-directory temporary state file, flush and close it, atomically replace the prior file, and report success only after replacement succeeds.
4. **AL-REQ-9.4:** WHEN the daemon restarts after a prior accepted sequence `N`, THE validator SHALL reject every candidate with `seq <= N` as `REPLAY`.
5. **AL-REQ-9.5:** WHEN startup finds a valid staged accepted record whose sequence equals persisted `last_accepted_seq` and no final inbox record exists, THE daemon SHALL validate the staged schema, promote it atomically, and publish it at most once before opening the audio source.
6. **AL-REQ-9.6:** IF a staged record is invalid or inconsistent with persisted state, THEN THE daemon SHALL enter `DEGRADED` and SHALL not open the audio source.
7. **AL-REQ-9.7:** IF `last_accepted_seq=4294967295`, THEN THE daemon SHALL fail closed for all further frames until explicit reprovisioning.
8. **AL-REQ-9.8:** WHEN sequence state is explicitly reprovisioned, THE operation SHALL be unavailable through ordinary UI controls and SHALL require pending COMMAND/AUTH state in the safety-gate subsystem to be cleared before listening resumes.

### AL-REQ-10 — Frequency anomaly reporting

**User story:** Sebagai operator, saya ingin tone drift dilaporkan terpisah dari integrity failure agar diagnosis tidak menyesatkan.

Acceptance criteria:

1. **AL-REQ-10.1:** WHEN a qualified mark or space estimate has an absolute deviation greater than 50 Hz from 1200 or 2200 Hz, THE modem SHALL emit a typed `FrequencyAnomaly` operational event containing source kind, expected frequency, measured frequency, absolute deviation, receiver state, and candidate correlation when available.
2. **AL-REQ-10.2:** IF absolute deviation is exactly 50 Hz, THEN THE modem SHALL not classify that estimate as a frequency anomaly.
3. **AL-REQ-10.3:** WHEN a candidate reaches telemetry validation, THE daemon SHALL set `source.frequency_deviation_hz` to the maximum qualified absolute deviation observed for that candidate.
4. **AL-REQ-10.4:** WHEN a frequency anomaly occurs, THE anomaly alone SHALL neither accept nor reject a frame; the frame verdict SHALL follow AL-REQ-5.
5. **AL-REQ-10.5:** IF an anomalous candidate later fails CRC, THEN THE daemon SHALL report its frame reason as `CRC` and the frequency observation as a separate anomaly; IF CRC is valid, THEN THE daemon SHALL not label the anomaly as a CRC failure.
6. **AL-REQ-10.6:** WHILE anomalous energy continues without a candidate, THE daemon SHALL emit at most one anomaly event per source per second using an injected clock.
7. **AL-REQ-10.7:** WHILE no contracted cross-process anomaly schema exists, THE daemon SHALL keep standalone `FrequencyAnomaly` events inside the typed process/diagnostic boundary and SHALL expose only schema-valid candidate deviation fields across process boundaries.

### AL-REQ-11 — Localhost-only network boundary

**User story:** Sebagai operator, saya ingin command path lokal tidak membuka koneksi non-loopback.

Acceptance criteria:

1. **AL-REQ-11.1:** WHEN the daemon starts its HTTP, WebSocket, or local RPC listener, THE network adapter SHALL bind explicitly to IPv4 `127.0.0.1` and SHALL not bind wildcard, LAN, public, or non-loopback IPv6 addresses.
2. **AL-REQ-11.2:** IF configuration requests a listener address other than `127.0.0.1`, THEN THE daemon SHALL reject startup before opening a socket.
3. **AL-REQ-11.3:** WHILE the daemon is running, THE acoustic command path SHALL create no outbound network socket.
4. **AL-REQ-11.4:** WHEN network-isolation acceptance tests inspect the daemon, MCP server, and AGC emulator processes, THE observed target SHALL be zero sockets outside `127.0.0.1`; the result SHALL remain labeled `TARGET` or `UNMEASURED` until evidence is stored.

### AL-REQ-12 — Observability and evidence integrity

**User story:** Sebagai reviewer, saya ingin status dan audit berasal dari runtime nyata agar klaim demo dapat diperiksa.

Acceptance criteria:

1. **AL-REQ-12.1:** WHEN a candidate attempt begins, changes state, or ends, THE daemon SHALL emit typed events containing event ID, injected wall-clock timestamp, source kind, receiver state, and candidate correlation ID without logging secret keys.
2. **AL-REQ-12.2:** WHEN validation ends, THE telemetry record SHALL contain raw frame hex when permitted by the telemetry schema, sequence when decoded, verdict, first reason, sample rate, and measured frequency deviation.
3. **AL-REQ-12.3:** WHEN operational status changes, THE daemon SHALL report `READY`, `DEGRADED`, or `STOPPED` using schema-valid `system.status` events if they cross the WebSocket boundary.
4. **AL-REQ-12.4:** IF SNR, latency, reliability, RAM, CPU, or property-case counts have no retained runner or measurement report, THEN THE UI and documentation SHALL display `UNMEASURED` or `TARGET` and SHALL not present a numeric result as measured or verified.
5. **AL-REQ-12.5:** WHEN a property or benchmark report is produced, THE report SHALL retain command, exit code, duration, seed where applicable, environment, and measured result.

### AL-REQ-13 — Performance and reliability targets

**User story:** Sebagai demonstrator, saya ingin target kinerja diuji dengan prosedur yang dapat diulang dan dilaporkan apa adanya.

Acceptance criteria:

1. **AL-REQ-13.1:** WHEN deterministic latency is measured, THE measurement SHALL run from the first preamble sample to final inbox promotion; the target SHALL be at most 2.0 seconds and the actual result SHALL be retained whether it passes or fails.
2. **AL-REQ-13.2:** WHEN room reliability is measured, THE trial SHALL send exactly 20 valid frames from a phone at 0.5 m in the recorded room setup; the target SHALL be at least 19 accepted frames and the actual count SHALL be retained.
3. **AL-REQ-13.3:** WHEN idle resource usage is measured on the development laptop, THE target SHALL be no more than 256 MB resident memory and no more than 10% process CPU, with sampling method and duration recorded.
4. **AL-REQ-13.4:** WHEN P1–P6 are reported, THE full profiles SHALL run P1=10,000, P2=500, P3=300, P4=10,000, P5=1,000, and P6=10,000 generated examples, and the report SHALL state that finite generated examples are evidence rather than proof over all possible inputs.
