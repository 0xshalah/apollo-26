# Requirements Document

## Feature: Mission Console

## Introduction

The mission-console feature contains the two browser surfaces for Apollo-26:

- `/ground` creates and acoustically transmits authenticated Apollo-26 `COMMAND` and `AUTH` frames.
- `/console` presents daemon-owned telemetry, AGC/DSKY state, audio spectrum, test evidence, and system status.

Both routes are static Next.js exports. The browser may validate input and present state, but it is not the source of truth for accepted sequences, AGC state, command authorization, safety decisions, or test evidence. `contracts/acoustic-frame-v1.md` is normative for binary frames. The JSON Schemas under `contracts/` are normative for WebSocket data.

## Glossary

- **Dashboard**: The Next.js + TypeScript + Tailwind application in `web-dashboard/`.
- **Ground Station**: The `/ground` route, normally opened on a phone or second computer.
- **Mission Console**: The `/console` route, normally served by the daemon on localhost.
- **Daemon**: The Python acoustic daemon that receives audio, owns accepted sequence persistence, runs the AGC emulator, serves static assets, and publishes WebSocket events.
- **Frame**: The normative 34-byte Apollo-26 acoustic frame.
- **COMMAND**: Frame type `0x01`, authenticated with the link key.
- **AUTH**: Frame type `0x02`, authenticated with the operator key and tied to a COMMAND by `ref_seq`.
- **DSKY**: The read-only console projection of daemon-owned AGC display, registers, and lamps.
- **Validated Event**: A WebSocket message that passes `contracts/websocket-events.schema.json`, including the nested telemetry schema where applicable.
- **Measured Fact**: A value backed by evidence whose status is `MEASURED` or `VERIFIED` in `docs/evidence-matrix.md`.
- **Unmeasured State**: A presentation state that says `UNMEASURED` instead of inventing a value.

## Requirements

### UI-REQ-1: Static application boundary

**User Story:** As a demo operator, I want the dashboard to run from static files so the daemon can serve it without a Node.js runtime.

#### Acceptance Criteria

1. THE Dashboard SHALL use Next.js, TypeScript, and Tailwind and SHALL configure `output: 'export'` with build output in `web-dashboard/out/`.
2. THE Dashboard SHALL provide statically exportable `/ground` and `/console` routes that work when `web-dashboard/out/` is served by the Daemon without `next dev`.
3. THE Dashboard SHALL NOT use SSR, Server Actions, Next.js API routes, dynamic cookies, rewrites, middleware, or any other Next.js server runtime feature.
4. WHERE Web Audio, Web Crypto, WebSocket, storage, media queries, or another browser API is needed, THE Dashboard SHALL access it only from a Client Component or an injected browser adapter.

### UI-REQ-2: Static hosting and asset resolution

**User Story:** As a developer, I want one static build strategy to support daemon hosting and the phone demo without broken asset paths.

#### Acceptance Criteria

1. THE Dashboard SHALL centralize `basePath` and asset-prefix configuration so daemon-hosted root paths and the configured GitHub Pages project path can each produce a valid static build.
2. WHEN either hosting mode is built, THE Dashboard SHALL resolve route navigation, JavaScript, CSS, local fonts, and public assets beneath that mode's configured base path.
3. THE Dashboard SHALL NOT require a runtime font, icon, script, telemetry, or styling request to a CDN.
4. WHEN the Daemon serves the export, THE Mission Console WebSocket endpoint SHALL be supplied through an explicit public build configuration or same-origin convention, not inferred from an undocumented production default.

### UI-REQ-3: Ground Station frame model and input

**User Story:** As a ground operator, I want typed COMMAND and AUTH forms so I can compose only protocol-valid frame candidates.

#### Acceptance Criteria

1. THE Ground Station SHALL provide separate, visibly identified `COMMAND` and `AUTH` modes with integer inputs that preserve wire units without floating-point conversion.
2. WHEN `COMMAND` mode is active, THE Ground Station SHALL require `seq`, `verb`, `noun`, `program`, `r1_centidegrees`, `r2_centidegrees`, and `delta_v_tenths_fps`; SHALL set `ref_seq` to zero; and SHALL support only the v1 command vocabulary `V25`, `V34`, and `V37` with programs `P00` and `P40` where applicable.
3. WHEN `AUTH` mode is active, THE Ground Station SHALL require a nonzero `seq` and `ref_seq`, SHALL set `flags`, `verb`, `noun`, `program`, `r1`, `r2`, and `delta_v` to zero, and SHALL explain that AUTH is one-time and tied to the referenced COMMAND.
4. IF any value is missing, non-integral, outside its wire range, or inconsistent with its frame type, THEN THE Ground Station SHALL block encoding and identify the field error before invoking Web Crypto or Web Audio.
5. THE Ground Station SHALL require the operator to enter the global sequence explicitly and SHALL describe the Daemon as the authority that accepts or rejects sequence freshness; browser storage SHALL NOT be presented as the authoritative sequence counter.

### UI-REQ-4: Exact 34-byte encoding

**User Story:** As a protocol developer, I want the browser encoder to match the normative Python wire format byte for byte.

#### Acceptance Criteria

1. WHEN a valid frame candidate is encoded, THE Ground Station SHALL produce exactly 34 bytes with sync `A5 26`, version `01`, the selected frame type, unsigned 32-bit big-endian `seq` and `ref_seq`, flags, payload, HMAC, and CRC at the offsets defined by `contracts/acoustic-frame-v1.md`.
2. WHEN signed payload fields are encoded, THE Ground Station SHALL encode R1 and R2 as big-endian 16-bit two's-complement integers and delta-v as a big-endian 32-bit two's-complement integer.
3. WHEN HMAC is calculated, THE Ground Station SHALL use HMAC-SHA256 over bytes 2 through 23 and place only its first eight bytes at offsets 24 through 31.
4. WHEN CRC is calculated, THE Ground Station SHALL use CRC-16/CCITT-FALSE over bytes 2 through 31 and place the big-endian result at offsets 32 through 33.
5. THE Ground Station SHALL display the actual encoded bytes and derived 8N1 bitstream; it SHALL NOT substitute illustrative or synthetic bits.

### UI-REQ-5: Browser key handling

**User Story:** As an operator, I want signing keys handled explicitly so static hosting does not expose operational secrets.

#### Acceptance Criteria

1. WHEN encoding a COMMAND, THE Ground Station SHALL obtain the link key from explicit session-only operator input; WHEN encoding an AUTH, it SHALL obtain the operator key from explicit session-only operator input.
2. THE Ground Station SHALL NOT embed operational keys in source, static bundles, URLs, analytics, logs, generated diagnostics, or persistent browser storage.
3. WHEN a frame has been signed or transmission is cancelled, THE Ground Station SHALL provide a direct way to clear the entered key and SHALL mask the key by default.
4. WHERE canonical demo keys are offered for a public demonstration, THE Ground Station SHALL label them as public demo material and SHALL keep that path visibly distinct from operational key entry.

### UI-REQ-6: Real Bell-202 transmission

**User Story:** As a ground operator, I want the browser to transmit the encoded frame as real Bell-202 audio that the daemon can decode.

#### Acceptance Criteria

1. WHEN the operator starts transmission after a user gesture, THE Ground Station SHALL use Web Audio to emit continuous-phase FSK with 1200 Hz mark for bit 1, 2200 Hz space for bit 0, and exactly 300 symbols per second.
2. WHEN transmitting, THE Ground Station SHALL emit at least 250 ms of continuous mark preamble followed immediately by all 34 frame bytes using 8N1 with LSB-first data bits and no inter-frame gap.
3. THE Ground Station SHALL modulate the exact bytes shown in the frame preview and SHALL expose real `idle`, `preparing`, `transmitting`, `completed`, and `failed` transmission states.
4. IF Web Audio is unavailable, blocked, suspended, or fails, THEN THE Ground Station SHALL stop safely, retain the composed frame, and present an actionable error without claiming transmission success.
5. THE Ground Station SHALL NOT offer 600- or 1200-baud operation.

### UI-REQ-7: Ground Station safety boundary

**User Story:** As a safety reviewer, I want the sender to avoid impersonating the backend safety gate.

#### Acceptance Criteria

1. THE Ground Station SHALL describe the `CRITICAL` flag as frame metadata and SHALL NOT present it as proof that a command is authorized or safe.
2. THE Ground Station SHALL NOT expose a client-side switch that disables mandatory AUTH, HMAC, sequence, frequency-anomaly, `KEY REL`, `OPR ERR`, or MCP safety-gate rules.
3. THE Ground Station SHALL NOT claim that an acoustically transmitted frame was accepted, authorized, or executed unless such a result is received through a separately validated daemon contract.

### UI-REQ-8: WebSocket trust boundary

**User Story:** As a console operator, I want every live update validated before it changes the display.

#### Acceptance Criteria

1. WHEN the Mission Console receives a WebSocket message, THE Dashboard SHALL parse and validate the complete message against `contracts/websocket-events.schema.json` and its referenced schema before updating application state.
2. IF JSON parsing or schema validation fails, THEN THE Mission Console SHALL leave the last valid projection unchanged and SHALL expose a bounded diagnostic that does not reproduce secrets or unbounded payload content.
3. THE Mission Console SHALL accept only schema version `1.0` and the event types `telemetry.frame`, `agc.state`, `audio.spectrum`, `test.summary`, and `system.status` defined by the current contract.
4. THE Dashboard SHALL derive TypeScript event types from, or test them for equality with, the JSON Schemas so hand-written types cannot silently drift from the runtime validator.

### UI-REQ-9: Connection lifecycle and event ordering

**User Story:** As a console operator, I want clear connection health and stable state when the daemon restarts or the link drops.

#### Acceptance Criteria

1. WHEN `/console` first loads, THE Mission Console SHALL show a connecting/loading state until validated events establish each panel's data.
2. IF the WebSocket disconnects, THEN THE Mission Console SHALL mark retained values as stale, show a disconnected state, and retry with capped exponential backoff and jitter without clearing the audit view.
3. WHEN a connection receives an `event_id` that is equal to or lower than the latest accepted ID for that connection, THE Mission Console SHALL ignore that duplicate or out-of-order event.
4. WHEN a new WebSocket connection is established, THE Mission Console SHALL reset connection-scoped event ordering and SHALL NOT infer cross-restart ordering, history completeness, or replay semantics that the contract does not define.
5. THE implementation task SHALL define the endpoint, initial snapshot behavior, heartbeat, and audit backfill with the Daemon owner before marking WebSocket integration complete.

### UI-REQ-10: Live DSKY dock

**User Story:** As a console operator, I want a persistent DSKY instrument that reflects the AGC emulator without becoming a second controller.

#### Acceptance Criteria

1. WHEN a valid `agc.state` event arrives, THE Mission Console SHALL update PROG, VERB, NOUN, R1, R2, R3, and the `COMP ACTY`, `UPLINK ACTY`, `KEY REL`, and `OPR ERR` lamps from that event only.
2. BEFORE the first valid `agc.state` event, THE DSKY dock SHALL show an explicit loading or unavailable state rather than zero-filled operational data.
3. THE DSKY dock SHALL be read-only and SHALL NOT mutate AGC state, clear lamps, send keys, authorize commands, or play a 900 Hz key click in response to a non-existent backend action.
4. THE Mission Console SHALL preserve the mockup's pinned desktop DSKY dock, compact quick access, phosphor readouts, hairline construction, and primary-instrument corner ticks while meeting the responsive requirements in UI-REQ-17.

### UI-REQ-11: Real acoustic spectrum

**User Story:** As a console operator, I want the acoustic visualization to show daemon-measured samples rather than animation.

#### Acceptance Criteria

1. WHEN a valid `audio.spectrum` event arrives, THE Mission Console SHALL render only the supplied `bin_hz`, `power_db`, and `sample_rate_hz` values.
2. IF `bin_hz` and `power_db` have different lengths, THEN THE Mission Console SHALL reject the event for visualization, preserve the prior valid spectrum as stale, and expose a bounded contract diagnostic rather than infer missing pairs.
3. BEFORE the first valid spectrum event, THE spectrum panel SHALL show loading or unavailable; WHILE disconnected, it SHALL show the last valid spectrum as stale.
4. THE Mission Console SHALL NOT render generated waveforms, synthetic spectrograms, orbital radar, lunar terrain, or other decorative data as telemetry.

### UI-REQ-12: Frame audit ledger

**User Story:** As a reviewer, I want accepted and rejected frames in a dense audit table so each validation outcome is traceable.

#### Acceptance Criteria

1. WHEN a valid `telemetry.frame` event arrives, THE Mission Console SHALL append a bounded audit row containing event time, source, available frame identity and command fields, validation gates, verdict, and stable reason code.
2. WHEN `frame` is null or a validation gate is null, THE audit ledger and detail inspector SHALL render the missing stage as unavailable and SHALL NOT invent decoded values or pass/fail results.
3. THE audit ledger SHALL preserve the mockup's hairline-separated table, horizontal overflow, sticky identity column, selected-row detail inspector, and loading, empty, populated, and error states.
4. THE audit ledger SHALL distinguish frequency deviation above 50 Hz as an acoustic anomaly and SHALL label CRC failure only when the telemetry reason is `CRC`.
5. THE audit ledger SHALL bound in-memory row retention and diagnostics so a long-running daemon cannot cause unbounded browser memory growth.

### UI-REQ-13: System, Flight Watch, and safety presentation

**User Story:** As a console operator, I want status indicators that report only states the daemon actually publishes.

#### Acceptance Criteria

1. WHEN a valid `system.status` event arrives, THE Mission Console SHALL display daemon, audio, AGC, and Flight Watch values using only the enums in the schema.
2. THE Mission Console SHALL NOT invent receiver substates, detailed Flight Watch substates, hook execution, safety-gate decisions, held-command lifecycle, or authorization status that are absent from validated events.
3. THE Mission Console SHALL NOT display editable safety toggles, fake hook triggers, configuration save controls, or a command composer.
4. WHERE a future panel needs hook, safety-gate, receiver-state, or command-lifecycle details, THE implementation SHALL first change and version the cross-process schema and its producers/consumers through the contract-change process.

### UI-REQ-14: Test results and evidence labels

**User Story:** As a judge, I want test and metric displays that distinguish targets from actual evidence.

#### Acceptance Criteria

1. WHEN a valid `test.summary` event arrives, THE Mission Console SHALL display its profile, passed, failed, skipped, and report path as the latest published test summary without adding fabricated counts, duration, seeds, properties, or pass claims.
2. BEFORE a valid `test.summary` event arrives, THE Mission Console SHALL show test evidence as `UNMEASURED` or unavailable and SHALL NOT simulate a PBT run in the browser.
3. THE Dashboard SHALL present a numeric claim as fact only when its evidence is `MEASURED` or `VERIFIED`; otherwise it SHALL use the exact `TARGET` or `UNMEASURED` label required by `docs/evidence-matrix.md`.
4. IF measured evidence misses a target or a test summary has failures, THEN THE Mission Console SHALL show the measured value or failure without replacing, hiding, or animating it into a passing result.
5. THE Dashboard SHALL NOT display the mockups' hard-coded SNR, latency, CRC rate, PBT totals, RAM, CPU, socket, or “100% offline” claims.

### UI-REQ-15: Visual language and content scope

**User Story:** As a product reviewer, I want the production UI to retain the mockups' instrument character while matching the approved product system.

#### Acceptance Criteria

1. THE Dashboard SHALL use Cosmic Void `#050608`, Lunar Titanium `#0a0d12` and `#0f141c`, Apollo Electrum Gold `#e6c875`, and DSKY Phosphor `#00ff88` as named Tailwind design tokens.
2. THE Dashboard SHALL load local Italiana for large headings, Syne for interface labels, and Space Mono for telemetry through `next/font` without runtime font requests.
3. THE Dashboard SHALL preserve one-pixel hairlines and restrained corner ticks around primary instruments, including the frame preview, spectrum or audit inspector, and DSKY dock.
4. THE Dashboard SHALL use English as the initial and fallback interface language.
5. THE Dashboard SHALL identify the emulator as an AGC-faithful subset with P00 and simplified P40 and SHALL NOT imply that it runs Luminary 99 or Colossus 249.

### UI-REQ-16: Explicit v1 exclusions

**User Story:** As a delivery owner, I want obsolete mockup features excluded so effort remains on the real end-to-end path.

#### Acceptance Criteria

1. THE Dashboard SHALL NOT offer V97, V06, V16, V35, 600 baud, or 1200 baud as supported v1 commands or modes.
2. THE Mission Console SHALL NOT include a command palette, settings panel, palette editor, orbital view, synthetic lunar visualization, interactive footer mast, standalone marketing landing page, fake hook panel, fake PBT runner, editable safety rules, or console command composer.
3. THE Dashboard SHALL NOT use constant arrays, timers, random values, generated canvases, or hard-coded sample rows to imitate live telemetry, evidence, AGC state, or successful transmission.
4. WHERE schedule tripwire T3 applies, THE Mission Console MAY reduce the acoustic visualization from a waterfall to real FFT bars and MAY reduce the route to the DSKY dock plus audit ledger, but it SHALL NOT substitute synthetic data.

### UI-REQ-17: Accessibility and responsive behavior

**User Story:** As an operator using a phone, keyboard, screen reader, zoom, or reduced motion, I want both routes to remain operable and legible.

#### Acceptance Criteria

1. THE Dashboard SHALL provide semantic landmarks, a skip link, programmatic labels and descriptions, visible keyboard focus, logical heading order, announced validation/connection/transmission errors, and keyboard operation for every interactive control.
2. THE Dashboard SHALL meet WCAG 2.2 AA contrast and SHALL NOT rely on color, animation, position, or sound alone to communicate state.
3. WHEN `prefers-reduced-motion: reduce` is active, THE Dashboard SHALL remove nonessential animation and auto-scrolling while preserving immediate state changes and transmission functionality.
4. ON coarse pointers or viewports below 64rem, THE Dashboard SHALL provide touch targets at least 44 by 44 CSS pixels and avoid hover-only disclosure.
5. ON narrow screens, THE Ground Station SHALL use a single-column flow without horizontal page scrolling; THE Mission Console SHALL collapse navigation and present the DSKY as an accessible slide-over or bottom sheet with focus containment, Escape/close behavior, and focus restoration.
6. WHEN the audit table exceeds the viewport, THE Mission Console SHALL confine horizontal scrolling to the table region and retain meaningful row and column associations for assistive technology.

### UI-REQ-18: TypeScript P9 and shared contracts

**User Story:** As a protocol maintainer, I want the TypeScript implementation checked against the same evidence as Python so protocol drift is detected.

#### Acceptance Criteria

1. THE Dashboard test suite SHALL load `contracts/vectors/frames.json` directly and SHALL verify both canonical accepted frames byte for byte without copying expected hex or protocol constants into a second fixture.
2. THE Dashboard test suite SHALL verify the vector-defined CRC mutation and replay expectations through the appropriate pure codec or validation oracle without claiming that the current unverified vectors are verified before both implementations pass.
3. THE Dashboard test suite SHALL implement P9 with fast-check over valid COMMAND and AUTH domain values and SHALL verify `decode(encode(value)) == value` for 10,000 generated cases under the full profile.
4. THE Dashboard test suite SHALL cover integer boundaries, COMMAND/AUTH semantic constraints, schema-valid and schema-invalid WebSocket events, reducer ordering, disconnect/stale states, null telemetry fields, unequal spectrum arrays, and evidence-label rendering.
5. WHEN protocol constants are represented in both Python and TypeScript, THE project SHALL include an equality test against the normative contract or shared vectors rather than relying on manually synchronized literals.

## Traceability and Source Priority

1. `contracts/acoustic-frame-v1.md` controls frame bytes, semantics, sequence rules, physical encoding, and validation reason codes.
2. `contracts/websocket-events.schema.json` and `contracts/telemetry-frame.schema.json` control live JSON accepted by `/console`.
3. `contracts/vectors/frames.json` supplies shared protocol examples and its verification status.
4. `docs/state-machines.md` controls receiver, DSKY, Flight Watch, and COMMAND/AUTH lifecycle behavior; the UI observes these states only where a schema exposes them.
5. `docs/evidence-matrix.md` controls metric wording and evidence status.
6. `PRD.md` v2.3.0 and `TASK.md` control product scope, design language, schedule reductions, and milestone dependencies.
7. `docs/archive/mockups/dashboard-page.html` and `landing-page.html` are visual mockups only and are not runtime, protocol, state, or evidence sources.
