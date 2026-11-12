---
inclusion: always
---

# Apollo-26 Structure & Boundaries

## Kepemilikan modul
| Modul | Memiliki | Tidak boleh memiliki |
| :-- | :-- | :-- |
| `acoustic/` | Frame codec, FSK modem, audio adapters, daemon, sequence persistence | Keputusan agen, aturan visual, state DSKY internal |
| `agc-core/` | Word 15-bit, memory/register, DSKY state machine, P00/P40 | Audio, filesystem, MCP, React |
| `mcp-server/` | MCP schemas/tools, orchestration adapter, safety gate | Demodulasi audio, UI, aturan yang hanya ada di prompt |
| `web-dashboard/` | `/ground`, `/console`, presentasi dan input operator | Sumber kebenaran AGC, enforcement safety, data hasil tes palsu |
| `contracts/` | Protokol dan schema lintas komponen | Implementasi runtime |
| `tests/` | Test lintas modul dan golden vectors | Kode produksi |

## Arah dependency
```text
web-dashboard ──WebSocket──► acoustic/daemon
mcp-server    ──local RPC──► acoustic/daemon
acoustic/daemon ───────────► agc-core
acoustic/frame ─────────────► (tidak bergantung modul aplikasi lain)
agc-core      ──────────────► (tidak bergantung acoustic/MCP/UI)
```

Dependency terbalik dari diagram di atas dilarang. `agc-core` dan codec frame harus dapat dites tanpa perangkat audio, jaringan, filesystem, atau Kiro.

## Sumber kebenaran state
- Sequence counter: daemon, persisten dan ditulis atomik.
- Validasi frame: `acoustic/frame.py`.
- Otorisasi perintah kritis: `mcp-server/safety_gate.py`.
- State AGC/DSKY: `agc-core`.
- UI hanya menampilkan snapshot melalui WebSocket; DOM/React state tidak boleh menentukan hasil keselamatan.
- Hasil tes: report yang dihasilkan test runner, bukan konstanta UI.

## Konvensi
- Satu tanggung jawab per modul; adapter I/O dipisahkan dari logika murni.
- Hindari import silang Python–frontend; kontrak bersama adalah schema dan golden vectors.
- Semua write telemetry memakai temp file + atomic rename.
- Error lintas boundary punya kode stabil dari kontrak, pesan manusia dapat berubah.
- Nama test menyebut requirement/property ID bila ada, misalnya `test_p6_rejects_replay`.