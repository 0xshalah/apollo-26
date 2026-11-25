# Product Requirements Document (PRD)

**Project Name:** Apollo-26  
**Tagline:** Acoustic Air-Gap Lunar Guidance Protocol & Telemetry Bridge  
**Competition:** Kiroween 2026 Hackathon (Kiro × Devpost)  
**Track:** Frankenstein Category  
**Document Version:** 2.3.0  
**Status:** Approved for Spec-Driven Development  
**Target Deadline:** December 4, 2026 @ 14:00 PT (December 5, 2026 @ 05:00 WIB)  
**Previous version:** [`docs/archive/PRD-v2.0.md`](docs/archive/PRD-v2.0.md)

---

## 0. Changelog

### v2.2 → v2.3
| # | Change | Reason |
| :-- | :-- | :-- |
| 15 | Runtime trigger `PostFileCreate` replaced by a **Flight Watch** session that calls `await_telemetry_frame()` | Kiro file hooks only fire when the agent creates a file, not when an external daemon writes a file. |
| 16 | Frame v1 clarified as 34 bytes with `frame_type`, `seq`, and `ref_seq` | An `AUTH` frame can now point explicitly to the sequence of the command it authorizes. |
| 17 | Added foundation steering, machine-readable contracts, state machines, threat model, and evidence matrix | Reduces ambiguity across Python–TypeScript and prevents claims without evidence. |

### v2.1 → v2.2
| # | Change | Reason |
| :-- | :-- | :-- |
| 12 | Frontend uses **Next.js + TypeScript + Tailwind** with `output: 'export'` (static), served by the Python daemon | Cleaner component structure and allows use of `magicui` / `react-bits`; judges still only need to install Python. |
| 13 | Added TypeScript-side PBT with `fast-check` (P9) | The JS frame encoder is tested against the same test vectors as Python. |
| 14 | 1200 baud mode and VERBs `V06` / `V16` / `V35` cut from v1 | Offsets the extra Next.js setup time (TASK.md §4 cut ladder, rungs 2 and 4). |

### v2.0 → v2.1

| # | Change | Reason |
| :-- | :-- | :-- |
| 1 | Hook changed from the fictional event `acoustic_carrier_detected` to `PostFileCreate` (+ blocking tool fallback) | Kiro only has IDE event triggers (`PostFileCreate`, `PreToolUse`, etc.). |
| 2 | Audio is listened to continuously by the **Acoustic Daemon**; the agent reads frames from a buffer | The agent needs a few seconds to wake up; by then the audio burst is over. |
| 3 | Bell-202 FSK modem written in-house (NumPy + `sounddevice`) | `fskmodem` is only a wrapper for `minimodem` (Linux/ALSA) and does not run on Windows. |
| 4 | AGC emulator = **in-house subset** (AGC-faithful), not running Luminary/Colossus | Realistic for 3 weeks; Virtual AGC is licensed GPL v2+, which conflicts with MIT if bundled. |
| 5 | Specs split per feature: `.kiro/specs/<fitur>/` | Kiro's built-in spec structure. |
| 6 | Latency targets split: deterministic path vs. agent path | LLM agent + 100 ms/key delay cannot be ≤ 2 seconds. |
| 7 | Added **HMAC + sequence counter** to every frame | CRC only detects corruption, not a fake sender or replay. |
| 8 | Metric claims rewritten in measurable form | "0 dB", "100% immune", "100% CRC" cannot be defended in front of judges. |
| 9 | Added WAV input & loopback modes | Judges may try it without a microphone or in a noisy room. |
| 10 | Safety rules enforced in **code** + `PreToolUse` hook; steering is guidance only | Steering does not technically block anything. |
| 11 | Critical command codes use real AGC VERBs (V37, V34) | V97 in v2.0 was not verified as "Engine Cut-off". |

---

## 1. Executive Summary & Vision

**Apollo-26** is an emergency telemetry control system that stitches together two computing eras 57 years apart:

1. **The Relic (1969):** The **Apollo Guidance Computer Block II** architecture: 15-bit word + 1 parity bit, *ones' complement* arithmetic, and the **DSKY** interface (VERB / NOUN / PROG, registers R1–R3, lamps `COMP ACTY`, `UPLINK ACTY`, `KEY REL`, `OPR ERR`).
2. **The Pilot (2026):** The **Kiro** AI agent working through the **Model Context Protocol (MCP)**, *Spec-Driven Development*, *Agent Hooks*, *Steering*, and *Property-Based Testing*.

The link between them is not Ethernet, Wi-Fi, or Bluetooth but **sound waves**: FSK modulation with Bell-202 tones (1200 Hz = bit 1 / *mark*, 2200 Hz = bit 0 / *space*), from the ground station speaker to the spacecraft microphone.

**Core claim (defensible):** the command path to the guidance computer **has no IP interface**. Every command must pass three deterministic gates (CRC-16, HMAC, sequence counter) and one code-based safety gate before it touches an AGC register. The Kiro agent acts as *Flight Director* and plans DSKY key sequences, but it **cannot** bypass those gates.

---

## 2. Problem Statement & Impact

### 2.1 Problem
* **IP-based command paths widen the attack surface.** Modern satellites increasingly use open network buses and protocols. If the ground station or link is compromised, an attacker can inject propulsion commands.
* **Unconstrained LLMs are dangerous for control systems.** A model can hallucinate register values, format data incorrectly, or run destructive commands.

### 2.2 Solution
* **No network interface on the command path:** the AGC emulator has no TCP/IP stack; the only command input is a validated acoustic frame.
* **Authenticated frames:** CRC-16 for integrity, HMAC-SHA256 for sender authenticity, sequence counter to reject *replay*.
* **Deterministic safety gate:** safety rules are implemented in MCP server code and tested with PBT. The agent cannot execute critical commands without operator authorization.

### 2.3 Acknowledged limitations (also written in the README)
* The acoustic channel can be eavesdropped on and disrupted (*jamming*) by anyone nearby. HMAC prevents forgery, not eavesdropping; the payload is not encrypted in v1.
* Kiro Agent uses a cloud LLM. The "offline" claim applies to the **command path** (daemon, MCP server, AGC emulator), not to the laptop as a whole.
* This is a proof of concept on an emulator, not a *flight-certified* system.

### 2.4 Impact Metrics (measurable)
| Metric | Target | How to prove it |
| :-- | :-- | :-- |
| IP interfaces on the command path | 0 | Daemon & MCP server bind only to `127.0.0.1`; tests ensure there are no outbound sockets. |
| Corrupt/forged frames executed | 0 across all PBT cases | PBT bit-flip, noise, and HMAC forgery (§9). |
| Emergency command triage time | ≤ 10 seconds (vs. ±20 minutes of manual calculation) | Measured in the demo: first tone → DSKY updated via the agent. |

---

## 3. System Architecture

```
┌───────────────────────────────────────────────┐
│ GROUND STATION (browser / phone)              │
│ web-dashboard → route /ground (Next.js static)│
│ - Command composer VERB/NOUN/PROG/ΔV          │
│ - Frame encoder + CRC-16 + HMAC (JS)          │
│ - Bell-202 FSK modulator (Web Audio API)      │
└──────────────────────┬────────────────────────┘
                       │  (((( sound in the air ))))
┌──────────────────────▼────────────────────────┐
│ ACOUSTIC DAEMON (Python, 127.0.0.1 only)      │
│ - Continuous microphone capture (sounddevice) │
│ - Detect 1200 Hz preamble ≥ 250 ms            │
│ - FSK demodulator (Goertzel) → bytes          │
│ - Validate CRC-16 → HMAC → sequence           │
│ - Valid frame  → telemetry/inbox/*.json       │
│ - Rejected frame → telemetry/rejected/*.json  │
│ - AGC + DSKY emulator (agc-core/)             │
│ - Local WebSocket → Mission Console           │
└──────────┬──────────────────────────▲─────────┘
           │ new file in inbox        │ localhost RPC
┌──────────▼──────────┐    ┌──────────┴─────────┐
│ KIRO FLIGHT WATCH   │◄──►│ MCP SERVER (stdio) │
│ await_telemetry_    │MCP │ mcp-server/        │
│ frame() + Specs     │    │ Safety gate (code) │
└─────────────────────┘    └────────────────────┘
                       ▲
┌──────────────────────┴────────────────────────┐
│ MISSION CONSOLE (route /console, localhost)   │
│ Live DSKY, spectrogram from real microphone,  │
│ frame audit log, hook & safety gate status    │
└───────────────────────────────────────────────┘
```

### 3.1 Components
| Component | Technology | Responsibility |
| :-- | :-- | :-- |
| Ground Station | Next.js (route `/ground`), Web Audio API, Web Crypto (HMAC-SHA256) | Composes & transmits frames. Can be opened on a phone over HTTPS (GitHub Pages). |
| Acoustic Daemon | Python 3.12+, NumPy, `sounddevice` | Listens, decodes, validates, stores frames; runs the AGC emulator; serves the frontend build output. |
| AGC Core | Pure Python | AGC Block II subset emulator + DSKY logic. |
| MCP Server | MCP Python SDK, stdio transport | Tools for the agent; enforces the safety gate. |
| Mission Console | Next.js (route `/console`), WebSocket to the daemon | Live visualization for the operator and the demo video. |

**Frontend rules:**
* Next.js with `output: 'export'`. No API routes, SSR, server actions, or middleware.
* The build output (`web-dashboard/out/`) is served by the Python daemon on `127.0.0.1`. Judges do not need Node.js; Node.js LTS is only for development.
* All live data comes from the daemon over a local WebSocket.

### 3.2 AGC Emulator (subset, "AGC-faithful")
What is **faithfully emulated**:
* 15-bit word + odd parity bit, *ones' complement* arithmetic (including −0), overflow.
* 2048-word erasable memory; registers A, L, Q, Z.
* DSKY input cycle: `VERB`, `NOUN`, `0–9`, `+`, `−`, `ENTR`, `PRO`, `CLR`, `RSET`, `KEY REL`; `OPR ERR` lamp for invalid input.
* Minimum 100 ms delay between keys (FR-10).

What is **simplified** (and stated honestly in the README):
* Does not run the original Luminary 99 / Colossus 249. Available programs: `P00` (idle), `P40` (SPS burn, simplified version).
* Supported VERB subset: `V25` (load 3 components into R1–R3), `V34` (terminate), `V37` (change program). `V06`, `V16`, `V35` are cut from v1.
* VERB/NOUN meanings are checked against the Virtual AGC documentation before release.

Stretch goal (only if time remains): an optional adapter to `yaAGC` as a separate process, not bundled in the repo.

---

## 4. Acoustic Protocol

### 4.1 Physical layer
* Bell-202 tones: mark 1200 Hz (bit 1), space 2200 Hz (bit 0), continuous phase.
* Baud rate: **300 baud** (the only mode in v1; 1200 baud is cut).
* Byte framing: asynchronous 8N1 (1 start bit, 8 data bits LSB-first, 1 stop bit).
* Preamble: continuous mark tone ≥ 250 ms, then the sync word.
* Sample rate: 48 kHz (fallback 44.1 kHz).

### 4.2 Frame format v1 (34 bytes)
| Offset | Field | Type | Description |
| :-- | :-- | :-- | :-- |
| 0 | `sync` | 2 bytes | `0xA5 0x26` |
| 2 | `version` | uint8 | `0x01` |
| 3 | `frame_type` | uint8 | `0x01` = `COMMAND`, `0x02` = `AUTH` |
| 4 | `seq` | uint32 BE | Global sequence; must be greater than the last accepted frame |
| 8 | `ref_seq` | uint32 BE | `0` for `COMMAND`; target command sequence for `AUTH` |
| 12 | `flags` | uint8 | bit0 = `CRITICAL`; other bits must be `0` in v1 |
| 13 | `verb` | uint8 | 0–99; `0` for `AUTH` |
| 14 | `noun` | uint8 | 0–99; `0` for `AUTH` when not relevant |
| 15 | `program` | uint8 | 0–99; `0` for `AUTH` |
| 16 | `r1` | int16 BE | Azimuth, units of 0.01° |
| 18 | `r2` | int16 BE | Elevation, units of 0.01° |
| 20 | `delta_v` | int32 BE | ΔV, units of 0.1 ft/s (fixed-point, no float) |
| 24 | `hmac` | 8 bytes | HMAC-SHA256 truncated to 64 bits, computed over bytes 2–23 |
| 32 | `crc` | uint16 BE | CRC-16/CCITT-FALSE over bytes 2–31 |

`COMMAND` is signed with `APOLLO26_LINK_KEY`; `AUTH` is signed with `APOLLO26_OPERATOR_KEY`. Normative details and test vectors are in [`contracts/acoustic-frame-v1.md`](contracts/acoustic-frame-v1.md).

Transmission duration at 300 baud (8N1): 34 bytes × 10 bits ÷ 300 ≈ 1.13 seconds + 0.25 second preamble ≈ **1.38 seconds**.

### 4.3 Validation order (deterministic, no LLM)
1. Sync word matches.
2. CRC-16 valid.
3. HMAC valid (shared key from the environment variable `APOLLO26_LINK_KEY`; an example demo key is in `.env.example`, the real key is never committed).
4. `seq` > last accepted `seq` (anti-replay).
5. Field ranges valid (VERB/NOUN/PROG 0–99, ΔV within the limits set in steering).

A frame that fails at any step is written to `telemetry/rejected/` along with the reason, then discarded without stopping the daemon.

---

## 5. Functional Requirements (EARS)

### 5.1 Acoustic link
* **FR-1 (Event-driven):** WHEN the daemon detects a continuous 1200 Hz tone for ≥ 250 ms, THE daemon SHALL start demodulating the frame and turn on the `UPLINK ACTY` lamp.
* **FR-2 (Unwanted behavior):** IF a frame fails any validation step in §4.3, THEN THE daemon SHALL discard the frame, log the reason to `telemetry/rejected/`, and keep running.
* **FR-3 (Ubiquitous):** THE daemon SHALL write every valid frame as one new JSON file in `telemetry/inbox/`.
* **FR-4 (Unwanted behavior):** IF the detected tone frequency deviates by more than 50 Hz from 1200/2200 Hz, THEN THE daemon SHALL log it as a telemetry anomaly.
* **FR-5 (Optional feature):** WHERE `--input <file.wav>` or `--loopback` mode is active, THE daemon SHALL process audio from that source with the same pipeline as the microphone.

### 5.2 Kiro agent & MCP
* **FR-6 (Event-driven):** WHEN the operator starts a Flight Watch session, THE agent SHALL call `await_telemetry_frame(timeout_sec)` and wait for a valid frame from the daemon through MCP.
* **FR-7 (Event-driven):** WHEN `await_telemetry_frame` returns a frame, THE agent SHALL call `inspect_agc_status()` before composing the DSKY key sequence.
* **FR-8 (Ubiquitous):** THE MCP server SHALL validate every `execute_dsky_sequence` call against the safety rules in code (`safety_gate.py`), regardless of what the agent decides.
* **FR-9 (Unwanted behavior):** IF the key sequence contains a critical command (§7.3), THEN THE MCP server SHALL refuse execution until a valid operator `AUTH` frame for that `seq` is received.

### 5.3 AGC emulator & DSKY
* **FR-10 (Ubiquitous):** THE emulator SHALL process DSKY key presses with a minimum delay of 100 ms and only when `KEY REL` is not lit.
* **FR-11 (State-driven):** WHILE `P40` is active, THE emulator SHALL display R1 (azimuth), R2 (elevation), R3 (ΔV) and turn on `COMP ACTY` periodically.
* **FR-12 (Unwanted behavior):** IF the key sequence is invalid according to DSKY logic, THEN THE emulator SHALL turn on `OPR ERR` and not change the program state.

---

## 6. Non-Functional Requirements

| Parameter | Target | Description |
| :-- | :-- | :-- |
| Deterministic path latency | ≤ 2.0 seconds | First tone → valid frame stored in inbox (300 baud). |
| Full path latency via agent | ≤ 10 seconds | First tone → DSKY registers updated. |
| Command path network isolation | 0 sockets outside `127.0.0.1` | Applies to the daemon, MCP server, emulator. |
| Decode reliability | ≥ 95% valid frames at 0.5 m speaker–microphone distance in an ordinary room | Measured and reported as-is in the README. |
| Resource | RAM ≤ 256 MB, CPU ≤ 10% while idle listening | Measured on the development laptop. |
| Platform | Windows 10/11 (primary), macOS/Linux (best effort) | The development laptop runs Windows. |
| Judge prerequisites | Python 3.12+, modern browser | Node.js not required. |
| Development prerequisites | + Node.js LTS | Python and Node.js are not yet installed on the development laptop. |

---

## 7. Kiro Feature Integration

### 7.1 MCP Server (`mcp-server/`)
| Tool | Function |
| :-- | :-- |
| `read_telemetry_frames(since_seq?)` | Reads valid frames from the inbox (already passed CRC/HMAC/seq). |
| `await_telemetry_frame(timeout_sec)` | Waits for a new frame in a Flight Watch session; this is the official runtime path. |
| `inspect_agc_status()` | Reads registers, the active program, and DSKY lamp status. |
| `plan_dsky_sequence(frame_seq)` | Deterministically converts a frame into a canonical key sequence (the agent can compare its plan). |
| `execute_dsky_sequence(keys, frame_seq)` | Sends keys to the emulator **after** passing `safety_gate`. |
| `verify_crc16(hex_payload)` | CRC verification utility for auditing. |

### 7.2 Agent Hooks (`.kiro/hooks/`)
| Hook | Trigger | Action |
| :-- | :-- | :-- |
| `flight-mode-shell-guard` | `PreToolUse`, `shell` category matcher | Block (exit 2) only when the file `telemetry/FLIGHT_MODE` exists. |
| `test-after-spec-task` | `PostTaskExec` | Run the related validation after a spec task finishes. |
| `pbt-on-save` | `PostFileSave`, matcher `(mcp-server|agc-core|acoustic)[\\/].*\.py$` | Run the fast test profile when the agent saves Python code. |

`PostFileCreate` is **not used as a runtime event bus** because Kiro file hooks only fire for files created by the agent. The operator starts a Flight Watch session, then the agent waits for frames through `await_telemetry_frame()`.

### 7.3 Steering (`.kiro/steering/`)
* `product.md`: product summary & claim limits.
* `tech.md`: stack, how to build/test, code conventions.
* `structure.md`: module boundaries, dependency direction, and state sources of truth.
* `agc-safety-rules.md`: rules for the agent, **mirrored** by `safety_gate.py`:
  1. Only use Apollo-26 MCP tools while processing frames.
  2. Do not run the shell while flight mode is active (enforced by the `flight-mode-shell-guard` hook).
  3. Must call `inspect_agc_status()` and make sure `KEY REL` is off before sending keys.
  4. Critical commands that require an operator `AUTH` frame:
     * `V37` (change program) while `P40` is active.
     * `V34` (terminate) while `P40` is active.
     * `P40` execution with |ΔV| above the set threshold.
  5. Frequency anomalies > 50 Hz must be mentioned in the agent report.

* `design-system.md`: `fileMatch` steering for `web-dashboard/**`, created before M5 from §8.

### 7.4 Specs (`.kiro/specs/`)

| Spec | Contents |
| :-- | :-- |
| `acoustic-link/` | FSK modem, frame format, validation, daemon. |
| `agc-emulator/` | 15-bit word, DSKY, P00/P40. |
| `mcp-bridge/` | MCP tools, safety gate, hooks. |
| `mission-console/` | Ground station & Mission Console. |

Each contains `requirements.md` (EARS), `design.md`, and `tasks.md`.

### 7.5 Kiro Powers (stretch goal)
Package the MCP server + `agc-safety-rules.md` steering as one Kiro Power so it can be reinstalled in one step.

---

## 8. Design System (Mission Console & Ground Station)

**Changed 12 Nov 2026 (operator decision):** the visual style follows the archived dashboard mockup (`docs/archive/mockups/dashboard-page.html`, "Console" theme: graphite, grotesk sans, amber accent). Full tokens and rules: `.kiro/steering/design-system.md`. The sample numbers, keypad, and out-of-scope verbs from the mockup are not used.

* **Colors:** graphite paper/ink, amber accent, blue (info), green (accepted/live), red (rejected/failed); oklch values in steering.
* **Typography:** *Host Grotesk* (UI and headings), *Atkinson Hyperlegible Mono* (telemetry).
* **Shape:** 8px cards, 6px controls, 4px tags; 1px borders.
* The previous style (Celestial Brutalism: Cosmic Void, Lunar Titanium, Electrum Gold, DSKY Phosphor; Italiana/Syne/Space Mono) is no longer used.
* **Interaction:**
  * Spectrogram and waterfall from **real microphone audio** streamed by the daemon, not synthetic patterns.
  * The bits transmitted by the ground station are the **actual frame encoding output**.
  * The PBT button in the console shows the last `pytest` result that was actually run, not an animation.
  * DSKY with a 900 Hz membrane click and lamps that follow the emulator state.
* **UI stack:** Tailwind for design tokens; `magicui` / `react-bits` components used sparingly and only those that run in a client component.
* **Design rules source:** `.kiro/steering/design-system.md` (`design.md` format, `inclusion: fileMatch` for `web-dashboard/**`).
* **UI v1 scope:** Acoustic Bridge, Frame Audit Log, Kiro Contracts & Hooks, PBT Results. The video storyboard and responsive preview are **not** part of the application.

---

## 9. Property-Based Testing (Hypothesis)

| # | Property | Level | Number of cases |
| :-- | :-- | :-- | :-- |
| P1 | `decode(encode(frame)) == frame` for all valid frames | Byte | 10,000 |
| P2 | Modulation → demodulation of clean audio returns an identical frame | Audio | 500 |
| P3 | Same as P2 with white noise at SNR ≥ 15 dB | Audio | 300 |
| P4 | Every single/double bit-flip on a frame → rejected | Byte | 10,000 |
| P5 | Random audio (noise, stray tones, clicks) never produces a frame that passes | Audio | 1,000 |
| P6 | Frame with wrong HMAC or old `seq` → rejected | Byte | 10,000 |
| P7 | For any AGC state and key sequence, a critical command without `AUTH` is never executed | Safety gate | 10,000 |
| P8 | 15-bit *ones' complement* arithmetic: `x + (−x) = −0`, commutative, consistent overflow | AGC | 10,000 |
| P9 | TypeScript frame encoder is identical to the Python test vectors, and `decode(encode(x)) == x` on the TS side (`fast-check`) | Byte (TS) | 10,000 |

A light `pytest` profile (≈ 100 cases/property) is used in the `pbt-on-save` hook; the full profile runs before release and its results are saved in `docs/pbt-report.md`.

---

## 10. Repository Structure

```text
apollo-26/
├── .kiro/                        # REQUIRED, must not be in .gitignore
│   ├── specs/
│   │   ├── acoustic-link/        # requirements.md, design.md, tasks.md
│   │   ├── agc-emulator/
│   │   ├── mcp-bridge/
│   │   └── mission-console/
│   ├── steering/
│   │   ├── product.md
│   │   ├── tech.md
│   │   ├── structure.md
│   │   ├── agc-safety-rules.md
│   │   └── design-system.md
│   ├── hooks/
│   │   ├── flight-mode-shell-guard.json
│   │   ├── test-after-spec-task.json
│   │   └── pbt-on-save.json
│   └── settings/mcp.json         # local MCP server registration
├── acoustic/                     # Daemon & modem
│   ├── modem.py                  # Bell-202 modulator/demodulator
│   ├── frame.py                  # Frame encode/decode, CRC, HMAC
│   └── daemon.py                 # Mic capture, inbox writer, local WebSocket
├── agc-core/
│   ├── word.py                   # 15-bit ones' complement word + parity
│   ├── agc_engine.py             # Registers & erasable memory
│   └── dsky.py                   # DSKY logic, P00/P40
├── mcp-server/
│   ├── server.py                 # MCP tools (stdio)
│   └── safety_gate.py            # Safety rule enforcement
├── web-dashboard/                # Next.js + TS + Tailwind, output: 'export'
│   ├── app/
│   │   ├── ground/page.tsx       # Ground station (can be opened on a phone)
│   │   └── console/page.tsx      # Mission Console
│   ├── lib/frame.ts              # Frame encoder + CRC + HMAC (TS)
│   ├── tests/                    # fast-check (P9)
│   ├── public/sample_burst.wav   # Sample frame for judges without a microphone
│   └── out/                      # Static build output, served by the daemon
├── tests/                        # Hypothesis PBT (P1–P8)
├── telemetry/                    # inbox/, rejected/ (contents in .gitignore, folders kept)
├── contracts/
│   ├── acoustic-frame-v1.md       # Normative binary contract
│   ├── telemetry-frame.schema.json
│   ├── websocket-events.schema.json
│   └── vectors/                   # Python ↔ TypeScript golden vectors
├── docs/
│   ├── state-machines.md
│   ├── threat-model.md
│   ├── evidence-matrix.md
│   └── archive/PRD-v2.0.md
├── .env.example                  # Demo HMAC keys
├── LICENSE                       # MIT
├── PRD.md
└── README.md
```

---

## 11. Alignment with Judging Criteria

* **Potential Impact:** a command path without an IP interface, with frame authentication and a safety gate proven through PBT. Limitations are written honestly.
* **Technological Implementation:** 4 EARS specs, 3 hooks (`PreToolUse`, `PostTaskExec`, `PostFileSave`), 5 focused steering files, a custom MCP server, cross-language contracts, and 9 PBT properties (Hypothesis + fast-check).
* **Design:** Mission Console in the "Console" dashboard style (mockup) with live data (real microphone, real emulator state).
* **Innovation:** a 1969 lunar lander computer and a 2026 AI agent that communicate only through sound.
* **Presentation:** video ≤ 3 minutes with two separate devices (phone as ground station, laptop as spacecraft).

### Video flow (180 seconds)
| Time | Scene |
| :-- | :-- |
| 0:00–0:20 | Problem: satellite commands over a network can be compromised. |
| 0:20–0:40 | Concept: 1969 × 2026 through sound. |
| 0:40–1:20 | Main demo: phone transmits a frame → live spectrogram → Flight Watch receives the frame through MCP → DSKY P40 updated. |
| 1:20–1:50 | Safety demo: forged frame rejected (HMAC), `V37` during burn blocked until the operator `AUTH` frame. |
| 1:50–2:20 | Kiro behind the scenes: EARS specs, steering, hooks, PBT results. |
| 2:20–3:00 | Measured metrics, limitations, and an invitation to try the repo. |

---

## 12. Execution Plan (12 Nov – 4 Dec 2026)

| Milestone | Date | Output | Done criteria |
| :-- | :-- | :-- | :-- |
| M0 Preparation | 12–13 Nov | Python/Node installed, public repo + MIT, 4 foundation steering files, contracts and assurance docs | Runtimes available; JSON contracts valid; public repo with detected license |
| M1 Risk spike | 13–14 Nov | Test 1200/2200 Hz tones phone → laptop mic | SNR/deviation recorded; demo distance decision goes into `design.md` |
| M2 Acoustic Link | 14–19 Nov | Modem, frame, daemon, P1–P6 | Frame from phone decoded on laptop |
| M3 AGC Emulator | 19–23 Nov | 15-bit word, DSKY, P00/P40, P8 | Sequence `V37 E 40 E` → P40 active in emulator |
| M4 MCP Bridge | 23–27 Nov | MCP tools, safety gate, 3 hooks, P7 | Full flow sound → agent → DSKY works |
| M5 Console & Ground Station | 27 Nov–1 Dec | Live UI, WAV sample | All panels show real data |
| M6 Video & Submission | 1–4 Dec | Public YouTube video, README, Devpost | Submission sent before 4 Dec 14:00 PT |
| Bonus | after submission | Blog, `#KiroweenHackathon26` post | Optional |

**Principle:** no new features or mockups before the main flow (sound → valid frame → agent → DSKY) is proven to work.
