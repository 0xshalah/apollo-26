# TASK.md — Apollo-26

Project-level work map, derived from [`PRD.md`](PRD.md) v2.1.0.
Detailed per-feature implementation tasks are created through the **Kiro Spec flow** in `.kiro/specs/<fitur>/tasks.md` at the start of each milestone. This file sets the order, dependencies, gates, and what gets cut when running late.

**Hard deadline:** 4 Dec 2026, 14:00 PT (5 Dec, 05:00 WIB) · **Submission target:** 3 Dec 2026
**Principle:** no new features or mockups before the main flow (sound → valid frame → agent → DSKY) is proven to work.

---

## 1. Summary & Status

| Milestone | Date | Estimate | Gate (must be proven) | Status |
| :-- | :-- | --: | :-- | :-- |
| M0 Preparation & contracts | 12–13 Nov | 8.5 h | Public repo + MIT, Python & Node running, contracts locked | ✅ public repo, MIT detected |
| M1 Risk spike | 13–14 Nov | 2.75 h | Hook & acoustic channel decisions recorded | 🟥 laptop's own speaker→mic test 0/20 (Windows default), 3/20 with enhancements off (13 Nov); phone → mic test not done; T1 trigger active |
| M2 Acoustic Link | 14–19 Nov | 27.5 h | Frame from phone arrives in `telemetry/inbox/` | 🟨 WAV & loopback 20/20; over-air 3/20 (13 Nov, enhancements off), target ≥95% not met |
| M3 AGC Emulator | 17–23 Nov | 20.5 h | `V37 E 40 E` → P40 active, R1–R3 correct | ✅ (also in live session) |
| M4 MCP Bridge | 23–27 Nov | 21.5 h | Sound → agent → DSKY ≤ 10 seconds; attacks rejected | 🟨 live Kiro session passed (V25 & P40+AUTH); agent latency 84 s, 10 s target missed |
| M5 Console (Next.js) | 26 Nov–1 Dec | 24.5 h | All panels use real data; static build served by daemon | 🟨 connected to real daemon (status, DSKY, audit, test summary); mic spectrum not visible yet |
| M6 Submission | 1–3 Dec | 16.5 h | Devpost submitted | ⬜ |
| **Total** | | **≈ 121.75 h** | | |

**Status 12 Nov (end of day):** Python suite 132 passed (including `slow`); full profile in `docs/pbt-report.md`; frontend 56 tests + P9 10,000 cases passed; live Kiro session passed for V25 and P40+AUTH; metrics in `docs/metrics.json`. Not yet: reliable over-the-air decoding (13 Nov: 3/20 with enhancements off), video, Devpost. Evidence details: `docs/evidence-matrix.md`.

**Capacity:** assumes 1 person × ±5 effective hours/day × 22 days ≈ 110 hours. About 4 hours of documentation groundwork is already done; the remaining plan still exceeds capacity. The cut ladder (§4) is part of the plan, not an emergency plan.

Legend: `[ ]` not done · `[x]` done · **(R)** risky · **⛔** on the critical path · `↳` depends on · `FR-x` / `Px` references point to the PRD.

---

## 2. Critical Path

```
0.1 Python ─► 1.2 tone test ─► 2.2 frame ─► 2.4 modem ─► 2.6 daemon ─► 3.8 integration ─► 4.4 MCP ─► 4.6 hook ─► 4.9 E2E ─► 6.5 video
3.3 word ─► 3.6 DSKY ─► 3.7 P40 ──────────────────────────────────────┘
```

* M3 (emulator) is pure Python with no audio, so it **can start in parallel** from 17 Nov while the modem is being tuned.
* M5 depends on the daemon (WebSocket) and the emulator, not on MCP. The Next.js scaffold (5.2) and TS encoder (5.3) can be done earlier if M2 stalls.

---

## 3. Tasks

Format of each task: **ID · title** · estimate · dependencies, followed by verifiable completion criteria.

### M0 — Preparation (12–13 Nov)

- [x] **0.1 ⛔ Install Python 3.12+** · 0.5 h
  - `winget install Python.Python.3.12`; done when `python --version` ≥ 3.12 in a new terminal.
- [x] **0.1b Install Node.js LTS** · 0.25 h
  - `winget install OpenJS.NodeJS.LTS`; done when `node --version` and `npm --version` run. Development only; judges do not need it.
- [x] **0.2 Virtual env & dependencies** · 0.5 h · ↳ 0.1
  - `.venv/` + `requirements.txt` (`numpy`, `sounddevice`, `mcp`, `hypothesis`, `pytest`) with pinned versions; `pip install -r requirements.txt` succeeds.
- [x] **0.3 Public GitHub repo** · 0.5 h — <https://github.com/0xshalah/apollo-26>, GitHub API: `public`, license `MIT`
  - `git init`, public repo `apollo-26`, MIT `LICENSE`; license shown in the *About* section.
- [x] **0.4 Safe `.gitignore`** · 0.25 h · ↳ 0.3
  - Ignores `.venv/`, `.env`, contents of `telemetry/inbox/` & `telemetry/rejected/` (folders kept via `.gitkeep`). Does **not** ignore `.kiro/`. Check: `git check-ignore .kiro` outputs nothing.
- [x] **0.5 Demo keys** · 0.25 h
  - `.env.example` contains example `APOLLO26_LINK_KEY` and `APOLLO26_OPERATOR_KEY`; the real `.env` is not committed.
- [x] **0.6 Foundation steering** · 2 h
  - `.kiro/steering/product.md`, `tech.md`, `structure.md`, `agc-safety-rules.md` created; `design-system.md` deferred until M5.
- [x] **0.6a Contracts & assurance docs** · 4 h
  - `contracts/acoustic-frame-v1.md`, two JSON Schemas, golden vectors, `docs/state-machines.md`, `threat-model.md`, and `evidence-matrix.md` created.
  - JSON is syntactically valid; golden vectors are still independent and must be verified by Python + TypeScript.
- [x] **0.7 First commit** · 0.25 h · ↳ 0.3–0.6a — commit `4ff0864`, 12 Nov
  - PRD, TASK, LICENSE, steering pushed. This is also the timestamp showing the project started after 30 Oct 2026.

### M1 — Risk spike (13–14 Nov)

- [x] **1.1 Kiro runtime event decision** · 0.25 h
  - `PostFileCreate` only fires when the agent creates a file, so it is not used for daemon output.
  - Official path: the operator starts a Flight Watch session → the agent calls `await_telemetry_frame()` through MCP.
  - Hooks are used for development guards and validation, not as a runtime event bus.
- [ ] **1.2 (R) ⛔ Phone → laptop acoustic channel test** · 2 h · ↳ 0.2
  - Phone plays 1200 and 2200 Hz tones; laptop records at 48 kHz; Goertzel distinguishes the two.
  - Record SNR and Hz deviation at distances of 0.3 m, 0.5 m, 1 m.
  - Done when: both tones are distinguishable at 0.5 m. If it fails, see trigger T1 (§4).
- [x] **1.3 Windows audio devices** · 0.5 h · ↳ 0.2 — default input "Microphone Array (Realtek)" and output "Speakers (Realtek)" support 48 kHz mono (MME)
  - `sounddevice.query_devices()` lists the microphone; 48 kHz is supported (or record the 44.1 kHz fallback).

### M2 — Acoustic Link (14–19 Nov) · spec `acoustic-link`

- [x] **2.1 Spec `acoustic-link`** · 3 h · ↳ 1.2
  - Created through the Kiro Spec flow (EARS requirements → design → tasks) from PRD §4 and FR-1–FR-5. Spike 1.2 results go into `design.md`.
- [x] **2.2 ⛔ `acoustic/frame.py`** · 3 h · ↳ 2.1
  - Encode/decode 34-byte frames, CRC-16/CCITT-FALSE, HMAC-SHA256 truncated to 8 bytes, `COMMAND`/`AUTH`, `seq`/`ref_seq`, ordered validation per the contract.
  - Verify the **test vectors** in `contracts/vectors/frames.json`; the TypeScript encoder in 5.3 must use the same vectors.
- [x] **2.3 PBT P1, P4, P6** · 2 h · ↳ 2.2 — full profile 10,000 examples/property passed (`docs/pbt-report.md`)
  - `pytest tests/test_frame.py` passes with the full profile (10,000 cases/property).
- [x] **2.4 ⛔ `acoustic/modem.py`** · 5 h · ↳ 2.2
  - Continuous-phase Bell-202 modulator, 8N1, preamble ≥ 250 ms, 300 baud default; Goertzel demodulator + bit synchronization.
- [x] **2.5 PBT P2, P3, P5** · 3 h · ↳ 2.4 — P2 500, P3 300, P5 1,000 examples passed; generation time 48 s / 30 s / 5 s (`docs/pbt-report.md`)
  - Passes with the case counts in PRD §9; full-profile run time recorded.
- [x] **2.6 ⛔ `acoustic/daemon.py`** · 4 h · ↳ 2.4
  - Continuous capture with a ring buffer; valid frame → `telemetry/inbox/<seq>.json`; rejected → `telemetry/rejected/` with the reason (FR-2, FR-3).
  - File writes are **atomic** (write to `.tmp`, then rename) so hooks never read a half-written file.
- [x] **2.7 `seq` persistence** · 1 h · ↳ 2.6
  - The last `seq` is saved to disk; restarting the daemon does not open a replay gap.
- [x] **2.8 Frequency anomaly > 50 Hz** · 1 h · ↳ 2.4 (FR-4)
- [x] **2.9 `--input` and `--loopback` modes** · 2 h · ↳ 2.6 (FR-5)
  - Create `web-dashboard/public/sample_burst.wav`; `python -m acoustic.daemon --input sample_burst.wav` produces a frame in the inbox.
- [x] **2.10 Network isolation test** · 0.5 h · ↳ 2.6
  - Automated test: all daemon sockets bind to `127.0.0.1`.
- [ ] **2.11 (R) Tuning in a real room** · 3 h · ↳ 2.6
  - 20 frames from the phone at 0.5 m; record the success rate. Target ≥ 95% (PRD §6).
- **M2 gate (19 Nov):** frame from the phone decodes correctly and appears in the inbox; P1–P6 green. If it fails, see trigger T2.

### M3 — AGC Emulator (17–23 Nov) · spec `agc-emulator`

- [ ] **3.1 Verify VERB/NOUN subset** · 1.5 h
  - Match `V25`, `V34`, `V37` and the NOUNs used against the Virtual AGC documentation; write the table + sources in `design.md`.
- [x] **3.2 Spec `agc-emulator`** · 2 h · ↳ 3.1
  - Kiro Spec flow from PRD §3.2 and FR-10–FR-12.
- [x] **3.3 ⛔ `agc-core/word.py`** · 2 h · ↳ 3.2
  - 15-bit word, odd parity, ones' complement (including −0), overflow.
- [x] **3.4 PBT P8** · 1 h · ↳ 3.3
- [x] **3.5 `agc-core/agc_engine.py`** · 2 h · ↳ 3.3
  - 2048-word erasable memory; registers A, L, Q, Z.
- [x] **3.6 ⛔ `agc-core/dsky.py`** · 5 h · ↳ 3.5
  - Key cycle, `COMP ACTY` / `UPLINK ACTY` / `KEY REL` / `OPR ERR` lamps, gap ≥ 100 ms, `OPR ERR` for invalid sequences (FR-10, FR-12).
- [x] **3.7 ⛔ Programs P00 & P40** · 4 h · ↳ 3.6
  - R1/R2/R3 updated and `COMP ACTY` blinks during P40 (FR-11).
- [x] **3.8 ⛔ Integration into the daemon** · 3 h · ↳ 2.6, 3.7
  - Emulator runs in the daemon process; local RPC (`127.0.0.1`) for the MCP server; WebSocket for the console.
- **M3 gate (23 Nov):** test script presses `V37 E 40 E`, then `V25` + data → P40 active and R1–R3 match the input.

### M4 — MCP Bridge & Hooks (23–27 Nov) · spec `mcp-bridge`

- [x] **4.1 Spec `mcp-bridge`** · 2 h · ↳ 3.8
  - Kiro Spec flow from PRD §7.1–7.3 and FR-6–FR-9; Flight Watch + `await_telemetry_frame` become the official runtime path.
- [x] **4.2 ⛔ `mcp-server/safety_gate.py`** · 3 h · ↳ 4.1
  - Critical commands (`V37` / `V34` during P40, |ΔV| > threshold) require a valid `AUTH` frame for the related `seq`.
- [x] **4.3 PBT P7** · 2 h · ↳ 4.2
- [x] **4.4 ⛔ `mcp-server/server.py`** · 4 h · ↳ 4.2
  - Tools: `read_telemetry_frames`, `await_telemetry_frame`, `inspect_agc_status`, `plan_dsky_sequence`, `execute_dsky_sequence`, `verify_crc16`.
- [x] **4.5 MCP registration** · 1.5 h · ↳ 4.4 — operator installed `.kiro/settings/mcp.json`; await/inspect/plan/execute/read called from a live Kiro session on 12 Nov
  - `.kiro/settings/mcp.json`; each tool is called once from Kiro chat and returns a correct result.
  - Status 12 Nov: the agent is not allowed to write `.kiro/settings/`. Template ready in `docs/kiro-mcp.json` (execute is not auto-approved, checked by a test). The operator copies it via *Kiro: Open workspace MCP config (JSON)*. The stdio server already passes `tests/test_mcp_stdio.py`.
- [x] **4.6 ⛔ Hooks** · 2 h · ↳ 4.5
  - Created through Kiro: `flight-mode-shell-guard`, `test-after-spec-task`, `pbt-on-save`. There is no runtime telemetry hook.
- [x] **4.7 Shell guard test** · 1 h · ↳ 4.6
  - Shell blocked when `telemetry/FLIGHT_MODE` exists, normal when it does not.
- [ ] **4.8 Agent prompt & steering** · 3 h · ↳ 4.6
  - Test 10 different frames; the agent always calls `inspect_agc_status` first and its plan matches `plan_dsky_sequence`. Fix the steering if it deviates.
- [ ] **4.9 ⛔ E2E test + attack scenarios** · 2 h · ↳ 4.8
  - Scenarios: (a) legitimate frame → DSKY updated ≤ 10 seconds, (b) forged HMAC frame → rejected, (c) old frame replay → rejected, (d) `V37` during P40 without `AUTH` → blocked, then passes after `AUTH`.
- [ ] **4.10 Backup recording** · 1 h · ↳ 4.9
  - Screen-record the E2E flow as is. This is the video safety net if M5–M6 run into problems.
- **M4 gate (27 Nov):** all four 4.9 scenarios pass twice in a row. If it fails, see trigger T3.

### M5 — Mission Console & Ground Station, Next.js (26 Nov–1 Dec) · spec `mission-console`

- [ ] **5.0 Design steering & motion skill** · 1 h
  - `.kiro/steering/design-system.md` in `design.md` format from PRD §8 (color tokens, typography, Tailwind rules), `inclusion: fileMatch` for `web-dashboard/**`.
  - Read the contents of `emilkowalski/skills` first, then install at user level (`~/.kiro/skills/`); remove after the project is done.
- [x] **5.1 Spec `mission-console`** · 1.5 h · ↳ 3.8, 5.0
- [x] **5.2 Static Next.js scaffold** · 4 h · ↳ 0.1b
  - Next.js + TypeScript + Tailwind, `output: 'export'`; no API routes, SSR, server actions, or middleware.
  - Daemon serves `web-dashboard/out/` on `127.0.0.1`; `/ground` and `/console` open from the daemon without `next dev`.
- [x] **5.3 `lib/frame.ts` + PBT P9** · 3 h · ↳ 2.2, 5.2
  - Frame encoder + CRC + HMAC (Web Crypto) in TypeScript.
  - `fast-check`: output identical to `contracts/vectors/frames.json` and round-trip passes 10,000 cases.
- [x] **5.4 Route `/ground`** · 4 h · ↳ 5.3
  - Command composer and Web Audio modulator.
  - Can send an **operator `AUTH`** frame; the key is entered manually in the UI, not embedded in code.
- [ ] **5.5 GitHub Pages** · 1 h · ↳ 5.4 — site live at <https://0xshalah.github.io/apollo-26/ground/> (branch `gh-pages`, `scripts/deploy_pages.cmd`, checked in headless Chrome); not yet: sound from the phone decoded by the daemon
  - `basePath` configured; `/ground` opens on the phone over HTTPS and its sound is decoded by the daemon.
- [ ] **5.6 Route `/console`** · 7 h · ↳ 3.8, 5.2
  - Live DSKY, spectrogram from the real microphone, frame audit log (inbox + rejected), hook & safety gate status, PBT results from `docs/pbt-report.md`.
  - `magicui` / `react-bits` components only if they save time; all inside client components.
- [ ] **5.7 Design polish** · 3 h · ↳ 5.6
  - Per `design-system.md`; take relevant visual elements from the `docs/archive/mockups/` mockups without fake data. Audit with the hallmark skill.
- **M5 gate (1 Dec):** no panel shows synthetic data or fake animation; the `out/` build runs from the daemon in a clean clone.

### M6 — Video & Submission (1–3 Dec)

- [x] **6.1 Full PBT report** · 1 h — `docs/pbt-report.md` from `scripts/pbt_full.cmd` (132 passed, seed 2026)
  - Results saved in `docs/pbt-report.md` (case counts, time, seed).
- [x] **6.2 Measure real metrics** · 2 h — `docs/metrics.json` via `scripts/measure_metrics.py`; over-air and agent missed the target, recorded as is
  - Deterministic latency, agent latency, decode reliability, RAM/CPU; written as is, including those that missed the target.
- [x] **6.3 README** · 3 h — quick start, P40+AUTH demo, "Measured so far" table, live console screenshot; video link still empty
  - Concept, architecture, installation, WAV mode for judges, acknowledged limitations (PRD §2.3), video link.
- [x] **6.4 Clean clone test** · 1.5 h · ↳ 6.3 — `scripts/clean_clone_check.cmd` 12 Nov: clone from GitHub, new venv, no Node; WAV accepted seq 1, replay rejected `REPLAY`, `out/console` present, 125 fast tests passed. The `/console` view in that clone has not been opened in a browser yet.
  - Clone into a new folder, follow the README from scratch **without Node.js**, run WAV mode until DSKY updates in `/console`. Fix every step that gets stuck.
- [ ] **6.5 ⛔ Video ≤ 3 minutes** · 6 h · ↳ 4.9
  - PRD §11 flow, two devices, no copyrighted music; upload to YouTube as **public**; check duration < 3:00.
- [ ] **6.6 Repo audit** · 0.5 h
  - Public, MIT detected, `.kiro/` complete (4 specs, 5 steering, 3 hooks, `mcp.json`), no real keys (`git log -p | Select-String APOLLO26_` contains only examples).
- [ ] **6.7 Devpost write-up** · 2 h — draft in `docs/devpost.md`; video script in `docs/video-script.md`
  - Description, Frankenstein category, *built with*, and an explanation of Kiro usage that references real files in `.kiro/` and `docs/kiro-journal.md`.
- [ ] **6.8 ⛔ Submit** · 0.5 h · **no later than 3 Dec**; keep 4 Dec as a buffer.

### Throughout the project

- [x] **J.1 Kiro journal** · ±10 minutes per milestone — `docs/kiro-journal.md` (no screenshots)
  - At the end of each milestone, write 3–5 points and 1–2 screenshots in `docs/kiro-journal.md`: specs created, hooks that fired, PBTs that caught bugs. Direct material for the video, Devpost, and blog.

### Bonus (after submission)

- [ ] **B.1** Blog article on the build process with Kiro (material from J.1).
- [ ] **B.2** Social media post `#KiroweenHackathon26`.
- [ ] **B.3** (Stretch) Package the MCP server + steering as a Kiro Power.
- [ ] **B.4** (Stretch) Optional adapter to `yaAGC` as a separate process.

---

## 4. Schedule Control

### Triggers (tripwire)
| ID | When checked | Condition | Action |
| :-- | :-- | :-- | :-- |
| T1 | 14 Nov | Tones not distinguishable at 0.5 m | Try an external speaker / full volume / 0.3 m distance. If it still fails: main demo over an audio cable, over-the-air test shown separately. |
| T2 | 19 Nov | M2 gate not passed | Freeze modem tuning, continue development using `--input` WAV mode; tuning continues in parallel for at most 1 hour/day. |
| T3 | 27 Nov | M4 gate not passed | Stop M5 polish; console is just DSKY + audit log. All time goes to E2E. |
| T4 | 1 Dec | Console not finished | Record the video with what already works; use backup recording 4.10 if needed. |

### Cut ladder (cut from the top when running late)
1. Bonus and stretch (B.1–B.4).
2. ~~1200 baud mode~~ **already cut 12 Nov** (covers the Next.js time).
3. Spectrogram waterfall → replaced by simple FFT bars.
4. ~~VERB `V06`, `V16`, `V35`~~ **already cut 12 Nov** (remaining `V25`, `V34`, `V37`).
5. Design polish 5.7 (use the base style from `design-system.md`).
6. `pbt-on-save` hook.
7. Ground station on phone → second laptop or the same laptop's speaker.

**Must not be cut:** `.kiro/` (specs, steering, main hooks), HMAC + `seq`, `safety_gate` + P7, real E2E flow, WAV mode for judges, README, video, MIT license.

---

## 5. Decision Log

| Date | Decision | Reason / evidence |
| :-- | :-- | :-- |
| 12 Nov | Self-built AGC subset emulator | Realistic for 3 weeks; Virtual AGC is GPL v2+ (PRD §0). |
| 12 Nov | Bell-202 modem written in-house | `fskmodem` depends on `minimodem` (Linux). |
| 12 Nov | Static Next.js frontend (`output: 'export'`) served by the daemon | User's choice; judges still only need Python. Costs +5 h in M5, partly covered by cutting ladder rungs 2 and 4. |
| 12 Nov | Design skills: design.md (format), hallmark (audit), emilkowalski/skills (motion); `magicui` / `react-bits` as component sources | Other repos overlap, do not fit the stack, are paid, or are licensed under Commons Clause. |
| 12 Nov | Flight Watch + `await_telemetry_frame`, no `PostFileCreate` runtime | Kiro documentation states the File Create hook only fires when the agent creates a file; external daemon output does not trigger the hook. |
| 12 Nov | Inspection window 5 s → 20 s (catalog v1.0 → v1.1) | Real Kiro session: the gap between agent tool calls is 5–30 s, so every plan was always `INSPECTION_STALE`. State changes are still detected through the AGC revision check in plan, gate, and daemon. The catalog version was bumped so mismatched daemon/MCP pairs fail closed with `CATALOG_MISMATCH`. |
| 12 Nov | AUTH hold 30 s → 120 s (catalog v1.2) | The window must cover the agent seeing HELD, the human operator sending AUTH, then the agent's await/inspect/plan/execute (5–30 s per call); 30 s was not enough, so critical commands always hit `AUTH_EXPIRED`. Operator key, `ref_seq` binding, single use, and sequence ordering are unchanged. Approved by the operator. |
| 12 Nov | `SystemClock` uses `perf_counter_ns` and `sleep_ms` waits until the deadline | The first live run failed at key 2/29 (`KEY_REJECTED`): on Python 3.12 Windows `time.monotonic` = GetTickCount64 (15.625 ms resolution), 10 of 40 `sleep(100 ms)` calls measured 93–94 ms. The 100 ms limit was not changed. Regression: `tests/test_system_clock.py`. Rerun: EXECUTED 29/29, R1/R2/R3 = 1250/420/3120. |
| 12 Nov | Critical P40 live test passed | COMMAND seq 2 (V37 P40, dv 312.0 ft/s) HELD; execute without AUTH rejected `AUTH_REQUIRED`; AUTH seq 3 MATCHED; EXECUTED 36/36, P40 active, R1/R2/R3 = 1250/420/3120. 84.2 s from COMMAND received until execute finished (one run, including negative tests). The daemon must run in the operator's terminal: Kiro's background terminal kills the process between turns. |
| 12 Nov | Frame v1 becomes 34 bytes | `frame_type` and `ref_seq` remove AUTH ambiguity; explicit 64-bit HMAC for the demo. |
| 13 Nov | Mission console polished one more step | Sticky command header summarizes frame window, latest seq, AGC display, Flight Watch; the empty spectrum now shows a 1200/2200 Hz reference ruler explicitly marked `not measured`; the latest-link snapshot summarizes frame/gate/source without replacing the AGC state; audit + system become a dense workspace. Real daemon check: 3 accepted + 1 replay rejected; header clipping at 375 px found and fixed with a deterministic two-row layout. |
| 12 Nov | Design-skill pass: curated, not stacked | `DESIGN.md` (Google format); Taste art direction; Impeccable craft audit; Hallmark anti-slop checks; Emil + official GSAP React guidance for scoped/reduced motion; Dimensional Drawing for frame anatomy. React Bits/Magic UI only references; OpenDesign, Scroll World, Canvas UI not integrated. Audit/licensing: `docs/design-sources.md`. |
| 12 Nov | Landing page polished one more step | The hero becomes a viewport-height mission briefing with a static grid/orbit; the live P40 card has packet bytes, a mini-DSKY, a gate timeline, and real results; sections use labels 01–06, main evidence becomes cards, and there is a closing CTA. All values still come from build-time reports; lint, typecheck, 65 tests, build, font/CDN/claim scan passed; checked at 1440×1100 and 375×1100. |
| 12 Nov | Landing page at `/` follows the landing mockup | The operator requested a landing page even though the phone sound flow has not worked yet; the "no landing before the main flow is done" rule in `product.md` is replaced by an honesty requirement. All numbers are read at build time from `docs/metrics.json` and `docs/test-summary.json` (`lib/landing-data.ts`, tested); missed targets show as FAILED. English. |
| 12 Nov | Dashboard mockup visual style adopted fully (replacing the PRD style) | The operator chose option B after seeing the layout result: graphite/amber/blue/green/red palette (oklch), Host Grotesk + Atkinson Hyperlegible Mono via `next/font`, 8/6/4 px corners. Data honesty rules still apply: no mockup sample numbers, keypad, or Verb 97. Design rules updated in `.kiro/steering/design-system.md`. |
| 12 Nov | Dashboard mockup-style layout, PRD visual style kept | Numbered sidebar, KPI strip, audit table with filters and search, right-side DSKY dock. KPIs only from frames actually received; no mockup numbers, DSKY keypad, or Verb 97. The daemon now also resends rejected frames when the console connects. Approved by the operator. |
| 12 Nov | Use the PRD visual style, not the old mockup palette | Cosmic Void + Lunar Titanium + Apollo Electrum Gold + DSKY Phosphor is more authentic and distinctive; Italiana only for large headings, Syne for UI, Space Mono for telemetry. |
| 12 Nov | Acoustic test from the same laptop's speaker → mic failed (0/20) | `scripts/measure_metrics.py`: 20 frames from the Realtek speaker, Realtek mic array, none detected. Probe recording: band energy at 1100–1300 Hz only 0.5–1% and at 2100–2300 Hz 0.1–0.2% of the total; dominant energy at 170–850 Hz. Not decoded at amplitude thresholds from 0.05 down to 0.002. Suspected cause: voice processing (array/SST) on the laptop mic suppresses steady tones; not proven yet. Trigger T1 active: test phone → laptop, turn off *audio enhancements*, or use an external mic. Loopback path still 20/20. |
| 13 Nov | Cause of 0/20 proven: Windows/Realtek voice processing | A steady 1200 Hz tone fades ~35 dB within 2 s; lowering the threshold to 0.0001 or using a 2 s preamble still fails, so it is not the modem. After *Audio enhancements*, noise suppression, and echo cancellation were turned off: steady tone (−1 dB), `measure_metrics.py` 20/20 detected, 3/20 accepted, 17 `LENGTH`; median 1.86 s. Modem code unchanged (threshold and preamble kept so P5 stays strong). README adds a step to turn off enhancements. Target ≥95% still FAILED; main demo stays on loopback. |
| 24 Nov | Soft-decision fallback for over-air; strict decoder stays the main path | Code analysis: one `UNKNOWN` symbol out of 340 fails the frame (`LENGTH`); frequency deviation measured on 13 Nov was only 0.01–0.06 Hz, so clock drift is not the cause. Added `acoustic/soft_decoder.py` (700–2900 Hz band-limit, tone detection over the middle 60% of the symbol, twist compensation from the `A5 26` sync, soft decisions, per-byte re-alignment) and `acoustic/recovery.py` (combining ≤3 copies, Chase ≤8 bits; CRC only selects candidates, HMAC remains the authority). The ground station sends 3× by default; identical copies ≤6 s = `DuplicateEvent`. Wire format v1 unchanged (contract §5.1). Channel model: strict 0/20, fallback 20/20. **Real over-the-air (laptop's own):** with Windows voice processing on, strict 0/20 and fallback 8–9/20. After the operator turned enhancements off again, 3× repeat: amplitude 0.4 → strict 18/20, fallback 20/20; amplitude 0.25 → strict 19/20, fallback 20/20. Target ≥95% reached for the laptop's own speaker (offline decode). Remaining: phone → laptop test at 0.5 m and live daemon from the microphone. First phone attempt (25 Nov, `corpus/phone-50cm/`, 90 s): no 1200/2200 Hz tones at all in the recording (1200 Hz band ≈0.007 throughout the file, equal to noise; laptop calibration gave 0.19), so the phone's sound was not captured or not transmitted. This is not a decoder test result. Phone-free substitute (25 Nov): live daemon from the microphone, laptop speaker, 20 frames × 3 → **19/20 accepted**, median 1.95 s (`docs/metrics.json`, landing rebuilt). Tools: `scripts/acoustic_lab.py calibrate|record|simulate|analyze`; option `--wasapi-exclusive`. |
| _14 Nov_ | _Acoustic demo distance & volume_ | _to be filled from 1.2 results_ |
