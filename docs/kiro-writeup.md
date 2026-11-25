# How Kiro was used to build Apollo-26

This write-up answers each question in the Kiroween 2026 submission requirements. Evidence paths point to files in this repository; the dated build log is in [`kiro-journal.md`](kiro-journal.md).

In short, Kiro wrote the code and also runs inside the system. A Kiro agent is the "flight director" that receives commands and plans key presses, and the Kiro features that shaped the build (specs, steering, hooks, MCP) also constrain that agent at run time.

## Kiro IDE, CLI, Web, Crew

We built everything in Kiro IDE on Windows: the four specs, the implementation, the live Flight Watch sessions, and the over-the-air debugging. The custom agent in `.kiro/agents/flight-director.json` uses the shared agent format (no CLI-only `hooks` field), so the same file loads in Kiro CLI. We did not use Kiro Web or Kiro Crew.

## Custom agents

`.kiro/agents/flight-director.json` and its prompt `flight-director-prompt.md` define Flight Director, the agent that runs Flight Watch.

- `tools: ["read", "@apollo26"]`: it sees only file-read tools and the six Apollo-26 MCP tools.
- `permissions`: `shell` and `fs_write` are `deny`; the five read-only MCP tools are `allow`; `execute_dsky_sequence` is `ask`, so a human approves every actuation.
- `resources`: the safety steering, the product rules, and the normative DSKY command catalog are attached to every session.

Before the custom agent existed, the rule "only MCP tools during Flight Watch" lived in steering text plus a hook that blocked the shell after the fact. Now the agent never sees a shell tool at all, and the hook still catches one if it ever appears.

## Agent hooks

Three hooks in `.kiro/hooks/`:

| Hook | Event | Workflow it automates |
| :-- | :-- | :-- |
| `flight-mode-shell-guard` | PreToolUse | While `telemetry/FLIGHT_MODE` exists (the MCP server writes it when Flight Watch starts), any shell tool call exits 2 and is blocked. |
| `pbt-on-save` | PostFileSave on `*.py` | Runs the fast property tests (`scripts/hooks/quick_tests.cmd`) after every Python edit. |
| `test-after-spec-task` | PostTaskExec | Runs the test suite after Kiro finishes a spec task, so a task is not "done" until tests pass. |

The shell guard fired in a live session: the agent tried to run tests while Flight Watch was active, the hook blocked it, and the agent had to ask the operator to end Flight Watch first. That was steering rule S-01 enforced by a hook. With `pbt-on-save`, the property tests run on every Python save instead of only before a commit.

## Spec-driven development

Four specs in `.kiro/specs/`, each with `requirements.md` (EARS), `design.md`, and `tasks.md`:

| Spec | Scope |
| :-- | :-- |
| `acoustic-link` | Bell-202 modem, frame codec, validation order, daemon |
| `agc-emulator` | 15-bit ones' complement words, DSKY state machine, P00/P40 |
| `mcp-bridge` | Flight Watch tools, canonical planner, safety gate, AUTH ledger |
| `mission-console` | `/console` and `/ground` behavior, data honesty rules |

The contracts came first (`contracts/acoustic-frame-v1.md`, JSON Schemas, the DSKY command catalog, golden vectors). Each spec then referenced the contract instead of restating constants. Requirement and property IDs (`AL-REQ-10`, `MCP-REQ-14`, `P7`) appear in test names, so `docs/evidence-matrix.md` can trace every requirement to a test.

Compared with vibe coding, the specs forced decisions that would otherwise have surfaced as bugs. First, the design review of the original PRD found that Kiro file hooks fire for files the agent creates, not files an external daemon writes. The idea of a hook waking the agent on a new frame could not work, so the spec replaced it with an `await_telemetry_frame` MCP call before any code existed. Second, the validation order (length → sync → version → CRC → flags → HMAC → replay → range) is written once in the contract and tested in Python and TypeScript against the same vectors, which is why the two encoders have never disagreed.

## Steering docs

Five steering files in `.kiro/steering/`:

- `product.md`: the pitch, and the allowed and banned claims. Kiro may only state a number as measured if `docs/evidence-matrix.md` says so; "100% secure", "0 dB", "100% offline" are banned.
- `agc-safety-rules.md`: the agent's Flight Watch rules S-01 to S-07 (tool boundary, inspect before act, canonical plan, critical AUTH, key cadence, anomaly reporting, no invented evidence).
- `tech.md` and `structure.md`: stack rules, module ownership, and dependency direction (`agc-core` must not import audio, MCP, or React).
- `design-system.md`: UI tokens, `fileMatch` on `web-dashboard/**` only.

The steering that helped most was about evidence. Every session inherited the rule that numbers come from stored reports. When the first over-the-air test decoded 0 of 20 frames, Kiro recorded it in the README and landing page as FAILED, and the landing page reads every figure from `docs/metrics.json` at build time. We also learned that steering guides the agent but enforces nothing. Each safety rule in steering has a code counterpart (`safety_gate.py`) and a test (P7). Steering tells the agent what to do, and the code makes the wrong action impossible.

## MCP

`mcp_server/` is a stdio MCP server with six tools: `await_telemetry_frame`, `read_telemetry_frames`, `inspect_agc_status`, `plan_dsky_sequence`, `execute_dsky_sequence`, `verify_crc16`. It talks to the daemon over a local RPC socket on `127.0.0.1`.

What MCP made possible: it is the boundary between a probabilistic agent and a deterministic machine. The agent can press a DSKY key only through `execute_dsky_sequence`. That tool recomputes criticality and the canonical key list itself, checks inspection freshness and AGC revision, and consumes a matching AUTH atomically. The daemon then checks everything again. `.kiro/settings/mcp.json` auto-approves only the read-only tools, and a test fails if `execute_dsky_sequence` is ever added to `autoApprove`.

Running the agent through the real MCP server found three bugs no unit test could. The 5 s inspection window was shorter than the agent's own tool-call latency. A 15.6 ms Windows clock made some 100 ms key gaps 93 ms. A 30 s AUTH window could not fit a human plus several model turns. We fixed each one by widening a time window and keeping the exact state check.

## Property-based testing

Hypothesis properties P1 to P8 and a fast-check property P9, all in the test suite:

| ID | Property |
| :-- | :-- |
| P1 | Frame bytes round-trip through encode/decode |
| P2 / P3 | Clean audio, and audio at SNR ≥15 dB, round-trip through the modem |
| P4 | Any bit flip is rejected |
| P5 | Random audio never yields a candidate or a key press |
| P6 | Wrong HMAC and replayed frames are rejected |
| P7 | A critical command without AUTH never executes |
| P8 | Ones' complement word invariants hold (plus a stateful AGC machine) |
| P9 | The TypeScript encoder matches Python on shared golden vectors |

The full profile ran 10,000 examples each for P1, P4, P6, P7, P8 and the stateful machine (`docs/pbt-report.md`). PBT caught a case the unit tests missed: a frame ending exactly at the buffer edge was not decoded, and the demodulator now pads 1/8 symbol. The P7 safety property is the reason we trust the gate with arbitrary agent input rather than a handful of hand-picked cases. When we later added CRC-guided bit repair for over-the-air audio, a randomized test (`test_recovered_candidates_from_garbage_are_never_accepted`) checks that repaired garbage still never passes HMAC.

## Kiro powers

`powers/apollo26-flight-watch/` packages the Flight Watch MCP server and its procedure as a Kiro Power in the Agent Plugins format: `plugin.json` (manifest and activation keywords), `mcp.json` (launches the server from the clone set in `APOLLO26_REPO`), and `skills/flight-watch/SKILL.md` (the inspect → plan → AUTH → execute procedure). Install it from the folder or the repository URL in the Powers panel. Anyone can then add the safety-gated DSKY tools to a Kiro session without copying our workspace config. The safety model stays the same, because the gate lives in the server, not in the Power.

We did not use third-party Powers for this build.

## What we would tell another team

- Put the safety rule in code and the procedure in steering. Steering made the agent behave; only the gate made misbehavior harmless.
- Run the real agent through the real MCP server early. Its latency is part of the protocol.
- Make evidence a steering rule. It kept every number in this submission honest, including the ones that missed their targets.
