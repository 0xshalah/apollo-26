---
inclusion: always
---

# Apollo-26 Technology Rules

## Stack
- Python 3.12+: acoustic daemon, codec, AGC emulator, MCP server.
- NumPy + sounddevice: DSP and audio I/O.
- MCP Python SDK: stdio server.
- pytest + Hypothesis: Python tests and PBT P1–P8.
- Next.js + TypeScript + Tailwind: frontend.
- fast-check: TypeScript PBT P9.

## Frontend
- `output: 'export'` is required; the build lands in `web-dashboard/out/` and is served by the Python daemon.
- Do not use SSR, Server Actions, dynamic cookies, rewrites, middleware, or Next.js runtime APIs.
- Web Audio, Web Crypto, WebSocket, and other browser APIs are used only in Client Components.
- Fonts are stored locally through `next/font`; no runtime font/CDN requests.

## Python
- Library code must not read env, the filesystem, the microphone, the clock, or the network implicitly. Those dependencies enter through a boundary/adapter.
- Use type hints on public APIs and domain values (`Enum`, dataclass) instead of free strings/dicts.
- Validate data once at the trust boundary, then use validated types.
- Do not catch `Exception` without logging context or translating it into a domain error.

## Contracts
- Normative binary format: `contracts/acoustic-frame-v1.md`.
- Cross-process JSON must pass the schemas in `contracts/*.schema.json`.
- Python and TypeScript implementations must use the same golden vectors in `contracts/vectors/`.
- Do not duplicate protocol constants without an equality test.

## Validation commands
- Fast Python: `python -m pytest -m "not slow"`
- Full Python: `python -m pytest`
- Frontend: `npm run lint && npm run typecheck && npm test -- --run && npm run build`

If a command does not exist yet, add it to the project configuration before marking a task done. Do not claim validation passed without keeping the output or exit code.
