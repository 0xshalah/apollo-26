---
inclusion: always
---

# Apollo-26 Technology Rules

## Stack
- Python 3.12+: acoustic daemon, codec, AGC emulator, MCP server.
- NumPy + sounddevice: DSP dan audio I/O.
- MCP Python SDK: server stdio.
- pytest + Hypothesis: test Python dan PBT P1–P8.
- Next.js + TypeScript + Tailwind: frontend.
- fast-check: PBT TypeScript P9.

## Frontend
- Wajib `output: 'export'`; hasil berada di `web-dashboard/out/` dan disajikan daemon Python.
- Dilarang memakai SSR, Server Actions, dynamic cookies, rewrites, middleware, atau API runtime Next.js.
- Web Audio, Web Crypto, WebSocket, dan browser API lain hanya dipakai dalam Client Components.
- Font harus disimpan lokal lewat `next/font`; jangan membuat request font/CDN saat runtime.

## Python
- Kode library tidak boleh membaca env, filesystem, microphone, clock, atau network secara implisit. Dependency tersebut masuk melalui boundary/adapter.
- Gunakan type hints pada API publik dan nilai domain (`Enum`, dataclass) alih-alih string/dict bebas.
- Validasi data hanya sekali pada trust boundary, lalu gunakan tipe tervalidasi.
- Jangan menangkap `Exception` tanpa mencatat konteks atau menerjemahkannya ke error domain.

## Kontrak
- Format biner normatif: `contracts/acoustic-frame-v1.md`.
- JSON lintas proses wajib lolos schema di `contracts/*.schema.json`.
- Implementasi Python dan TypeScript wajib memakai golden vector yang sama di `contracts/vectors/`.
- Jangan menduplikasi konstanta protokol tanpa test kesetaraan.

## Perintah validasi (diisi setelah scaffold)
- Python cepat: `python -m pytest -m "not slow"`
- Python penuh: `python -m pytest`
- Frontend: `npm run lint && npm run typecheck && npm test -- --run && npm run build`

Jika perintah belum ada, tambahkan ke konfigurasi proyek sebelum menandai tugas selesai. Jangan mengklaim validasi lolos tanpa menyimpan output atau exit code.