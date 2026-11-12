# Apollo-26 web dashboard

Static Next.js (App Router) export with three routes:

- `/` links to the two tools.
- `/ground/` composes COMMAND/AUTH frames (V37 P00/P40, V25 N81, V34), signs them with keys typed at runtime, shows the exact 34 bytes and 8N1 bits, and plays them as 300-baud Bell-202 audio.
- `/console/` is a read-only view of the daemon over a same-origin WebSocket (`/ws`). Every message is validated against `../contracts/*.schema.json` (Ajv, bundled at build time). With no data it shows `AWAITING`, `UNMEASURED`, or `DISCONNECTED`.

There is no server runtime. The daemon serves `out/` on `127.0.0.1`.

## Commands

```powershell
$env:Path = "$env:LOCALAPPDATA\Programs\nodejs;" + $env:Path   # portable Node.js
npm install
npm run dev          # development server
npm run lint
npm run typecheck
npm test             # vitest run; P9 fast profile (300 cases per property)
npm run test:full    # P9 full profile (10,000 cases per property)
npm run build        # static export to out/ (out/ground/index.html, out/console/index.html)
```

`scripts/run-logged.ps1 -Log logs/<name>.log <command>` runs a command and saves its output and exit code.

## Build configuration

| Variable | Default | Use |
| :-- | :-- | :-- |
| `NEXT_PUBLIC_BASE_PATH` | `""` | Set to `/apollo-26` (repo name) for GitHub Pages. |
| `NEXT_PUBLIC_APOLLO26_WS_PATH` | `/ws` | WebSocket path on the page's origin. |

Fonts (Italiana, Syne, Space Mono) are fetched by `next/font/google` during `npm run build` and served from `out/`. The build needs network access; the exported site makes no font or CDN requests.

## Keys

No key is bundled. The "Use public demo keys" button loads the demo keys published in `contracts/vectors/frames.json`. Those keys are public, so anyone can forge frames with them. Keys live only in tab memory. The page stores only the last transmitted `seq` in `localStorage`, as a convenience; the daemon decides whether a sequence is fresh.

## Layout

- `lib/frame.ts`: 34-byte codec, CRC-16/CCITT-FALSE, HMAC-SHA256 truncated to 8 bytes (Web Crypto adapter injected).
- `lib/modem.ts`: Bell-202 symbol plan, phase-continuous PCM, Web Audio playback.
- `lib/events.ts`: WebSocket trust boundary (schema validation, bounded diagnostics).
- `lib/console-state.ts`: pure reducer (ordering, stale state, retention limits, backoff).
- `lib/ground-form.ts`: form parsing at the input boundary.
- `tests/`: golden vectors from `../contracts/vectors/frames.json`, P9 round-trip, modem, schema, reducer, and form tests.
