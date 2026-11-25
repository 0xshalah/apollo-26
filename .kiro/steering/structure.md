---
inclusion: always
---

# Apollo-26 Structure & Boundaries

## Module ownership
| Module | Owns | Must not own |
| :-- | :-- | :-- |
| `acoustic/` | Frame codec, FSK modem, audio adapters, daemon, sequence persistence | Agent decisions, visual rules, internal DSKY state |
| `agc-core/` | 15-bit word, memory/registers, DSKY state machine, P00/P40 | Audio, filesystem, MCP, React |
| `mcp-server/` | MCP schemas/tools, orchestration adapter, safety gate | Audio demodulation, UI, rules that exist only in a prompt |
| `web-dashboard/` | `/ground`, `/console`, presentation and operator input | AGC source of truth, safety enforcement, fake test results |
| `contracts/` | Cross-component protocol and schemas | Runtime implementation |
| `tests/` | Cross-module tests and golden vectors | Production code |

## Dependency direction
```text
web-dashboard ──WebSocket──► acoustic/daemon
mcp-server    ──local RPC──► acoustic/daemon
acoustic/daemon ───────────► agc-core
acoustic/frame ─────────────► (depends on no other application module)
agc-core      ──────────────► (does not depend on acoustic/MCP/UI)
```

Dependencies in the reverse direction of the diagram are forbidden. `agc-core` and the frame codec must be testable without audio devices, network, filesystem, or Kiro.

## State sources of truth
- Sequence counter: daemon, persistent and written atomically.
- Frame validation: `acoustic/frame.py`.
- Critical-command authorization: `mcp-server/safety_gate.py`.
- AGC/DSKY state: `agc-core`.
- The UI only shows snapshots over WebSocket; DOM/React state must not decide safety outcomes.
- Test results: reports produced by the test runner, not UI constants.

## Conventions
- One responsibility per module; I/O adapters are separate from pure logic.
- Avoid Python–frontend cross imports; the shared contract is the schemas and golden vectors.
- Every telemetry write uses a temp file + atomic rename.
- Cross-boundary errors have stable codes from the contract; human messages may change.
- Test names mention the requirement/property ID when there is one, for example `test_p6_rejects_replay`.
