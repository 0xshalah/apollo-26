# Apollo-26 Evidence & Traceability Matrix

Dokumen ini mencegah requirement hilang dan klaim tanpa bukti. Perbarui setelah setiap milestone.

## Status
- `PLANNED`: belum diimplementasikan.
- `IMPLEMENTED`: kode ada, belum diverifikasi penuh.
- `MEASURED`: nilai berasal dari pengukuran tersimpan.
- `VERIFIED`: acceptance test/property lolos dan bukti tersedia.
- `FAILED`: bukti nyata tidak mencapai target; tampilkan apa adanya.

UI dan materi kompetisi **hanya boleh menyajikan angka sebagai fakta** jika statusnya `MEASURED` atau `VERIFIED`. Selain itu gunakan label `TARGET` atau `UNMEASURED`.

## Bukti terakhir
12 Nov 2026, Windows 10 21H1 / build 19043, Python 3.12.10, Node 26.13.1:
- `scripts\pytest.cmd` (semua tes, termasuk `slow`, profil `dev`): **132 passed**, exit 0.
- `scripts\pbt_full.cmd` (profil `full`, `max_examples=10000`, seed 2026): lihat `docs/pbt-report.md`; ringkasan `docs/test-summary.json` dipublikasikan daemon ke panel tes console.
- Sesi Kiro live (12 Nov): V25 N81 seq 1 EXECUTED 29/29; P40 seq 2 ditolak `AUTH_REQUIRED` tanpa AUTH, lalu EXECUTED 36/36 dengan AUTH seq 3. Sumber: hasil tool MCP dan log daemon.
- `web-dashboard`: `npm run lint && npm run typecheck && npm test -- --run && npm run build` exit 0 (56 tes); `npm run test:full` (P9, 10.000 kasus/properti) exit 0. Log: `web-dashboard/logs/`.
- CLI nyata: `scripts\smoke_cli.cmd` — `sample_burst.wav` diterima sebagai seq 1, pemutaran ulang ditolak `REPLAY`.
- Uji akustik fisik pertama (speaker → mikrofon laptop yang sama, 20 frame): 0/20 terdeteksi (`docs/metrics.json`, `acoustic_self_test_previous`). Semua tes otomatis audio memakai PCM sintetis dari modem asli.
- 13 Nov, penyebab 0/20: rekaman nada 1200 Hz stabil memudar sekitar 35 dB dalam 2 s karena pemrosesan suara Windows/Realtek, sehingga preamble 250 ms tidak pernah memenuhi syarat. Bukan bug modem.
- 13 Nov, uji ulang dengan *Audio enhancements*, noise suppression, dan echo cancellation mati (dilaporkan operator): 20/20 terdeteksi, **3/20 diterima**, 17 ditolak `LENGTH`; nada pertama → diterima median 1,86 s (min 1,83, maks 1,93) pada 3 frame itu (`docs/metrics.json`, `acoustic_self_test`). Tidak ada frame rusak yang diterima.
- `/console` diuji di Chrome headless terhadap daemon nyata: status, DSKY, ringkasan tes, dan baris audit dari frame loopback tampil (`docs/images/console-live.png`).

## Requirements
| ID | Ringkasan | Design owner | Implementasi | Verifikasi | Bukti | Status |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| FR-1 | Preamble ≥250 ms memulai demodulasi | `acoustic-link/design.md` | `acoustic/modem.py`, `receiver.py` | `test_al_req_1_3_*`, `test_al_req_2_*`, E2E | pytest | VERIFIED (sintetis) |
| FR-2 | Frame gagal dibuang + diaudit; daemon hidup | `acoustic-link/design.md` | `acoustic/frame.py`, `daemon.py` | P4, P5, P6, `test_threat_2/3/4` | rejected JSON | VERIFIED |
| FR-3 | Frame valid ditulis atomik ke inbox | `acoustic-link/design.md` | `acoustic/telemetry_store.py` | `test_threat_1`, smoke CLI | inbox JSON | VERIFIED |
| FR-4 | Drift >50 Hz dicatat sebagai anomali | `acoustic-link/design.md` | `acoustic/modem.py` | `test_al_req_10_*` | pytest | VERIFIED (unit) |
| FR-5 | WAV/loopback lewat pipeline sama | `acoustic-link/design.md` | `acoustic/audio.py`, `daemon.py` | smoke CLI `--input`, harness loopback | `sample_burst.wav` | VERIFIED |
| FR-6 | Flight Watch menunggu frame via MCP | `mcp-bridge/design.md` | `mcp_server/service.py` | `test_e2e_flight_watch.py`, `test_mcp_stdio.py`, sesi Kiro live 12 Nov (seq 1 V25 N81 via WAV; seq 2 P40 + AUTH seq 3 via loopback) | pytest + audit MCP | VERIFIED (live, sumber WAV/loopback; mikrofon fisik belum) |
| FR-7 | Inspect AGC sebelum planning | `mcp-bridge/design.md` | `mcp_server/safety_gate.py` | `test_mcp_req_inspect_before_act_is_enforced` | pytest | VERIFIED |
| FR-8 | Setiap execute melewati safety gate | `mcp-bridge/design.md` | `safety_gate.py` + guard daemon | P7, `test_daemon_refuses_direct_rpc_*` | pytest | VERIFIED |
| FR-9 | Perintah kritis wajib AUTH terkait | `mcp-bridge/design.md` | `safety_gate.py`, `ledger.py` | P7, `test_threat_5/6`, expiry test, sesi Kiro live 12 Nov: seq 2 P40 ditolak `AUTH_REQUIRED` tanpa AUTH, lalu EXECUTED 36/36 setelah AUTH seq 3 `MATCHED` | pytest + audit MCP | VERIFIED |
| FR-10 | Key cadence ≥100 ms dan KEY REL aman | `agc-emulator/design.md` | `agc_core/agc_engine.py` | stateful PBT, `test_agc_req_6/7_*`, `test_system_clock.py` (clock asli) | pytest | VERIFIED |
| FR-11 | P40 memperbarui R1–R3 + COMP ACTY | `agc-emulator/design.md` | `agc_core/agc_engine.py` | `test_agc_prop_6/8_*`, `test_threat_5`; live: P40 aktif, R1/R2/R3 = 1250/420/3120 | pytest + inspect MCP | VERIFIED (R1–R3 live; kedip COMP ACTY hanya di test) |
| FR-12 | Urutan invalid → OPR ERR tanpa state change | `agc-emulator/design.md` | `agc_core/agc_engine.py` | `test_agc_prop_4/5_*`, stateful PBT | pytest | VERIFIED |

## Properties
| ID | Property | Test target | Status |
| :-- | :-- | :-- | :-- |
| P1 | Frame byte round-trip | `tests/test_frame.py` | VERIFIED |
| P2 | Audio bersih round-trip | `tests/test_modem.py` | VERIFIED |
| P3 | Audio SNR ≥15 dB round-trip | `tests/test_modem.py` (`slow`) | VERIFIED |
| P4 | Bit flip ditolak | `tests/test_frame.py` | VERIFIED |
| P5 | Audio acak tidak menghasilkan kandidat / tombol | `tests/test_modem.py`, `test_threat_7` | VERIFIED |
| P6 | HMAC salah/replay ditolak | `tests/test_frame.py`, `test_threat_3/4` | VERIFIED |
| P7 | Critical tanpa AUTH tidak execute | `tests/test_p7_safety_gate.py`, `test_daemon_refuses_direct_rpc_*` | VERIFIED |
| P8 | Invariant ones' complement | `tests/test_word.py`, `tests/test_agc_stateful.py` | VERIFIED |
| P9 | Python–TypeScript encoder setara | `web-dashboard/tests/p9-frame.test.ts` | VERIFIED |

Catatan jumlah kasus: profil `dev` Hypothesis = 100 contoh/properti (dipakai hook dan CI); profil `full` dijalankan 12 Nov (`docs/pbt-report.md`, 132 passed, exit 0). P1, P4, P6, P7, P8 dan mesin stateful AGC = 10.000 contoh lulus per properti; properti modem memakai batas sendiri: P2 = 500, P3 = 300, P5 = 1.000. Jangan menyebut "10.000 kasus" untuk P2, P3, P5.

## Competition claims
| Claim | Target | Metode | Evidence path | Status | Copy yang boleh tampil sekarang |
| :-- | :-- | :-- | :-- | :-- | :-- |
| Command path tidak membuka socket keluar | 0 di luar `127.0.0.1` | listener bind test + host guard test | `test_listeners_bind_only_to_loopback`, `test_dns_rebinding_*` | IMPLEMENTED (listener terverifikasi; inspeksi socket keluar belum) | `Listeners bind only to 127.0.0.1 (tested)` |
| Frame korup/palsu dieksekusi | 0 pada suite | P4/P6/P7 + E2E abuse | `tests/test_e2e_flight_watch.py` | VERIFIED (dev profile) | `Corrupted, forged, and replayed frames are rejected in tests` |
| Latensi deterministik | ≤2.0 s | nada pertama → inbox timestamp | `docs/metrics.json` (`loopback_processing`) | MEASURED (loopback 20/20: proses median 0,588 s, maks 0,892 s); over-air MEASURED pada 3 frame yang diterima (13 Nov, enhancements mati): median 1,86 s, maks 1,93 s; sampel terlalu kecil untuk klaim umum | `Loopback decode + validation: median 0.59 s over 20 frames (measured)` |
| Latensi penuh via agen | ≤10 s | COMMAND diterima → AGC postcondition | `docs/metrics.json` (`agent_path_live`) | MEASURED, **meleset**: 84,2 s (1 run P40+AUTH, termasuk percobaan tanpa AUTH yang sengaja ditolak) | `Agent path: 84 s in one live run (target 10 s not met)` |
| Decode pada 0.5 m | ≥95% dari 20 frame | controlled trial | `docs/metrics.json` (`acoustic_self_test`) | FAILED (speaker → mic laptop yang sama: 0/20 terdeteksi dengan bawaan Windows; 3/20 diterima dengan enhancements mati, 13 Nov); uji HP 0,5 m belum dijalankan | `Over the air: 3 of 20 frames accepted on one laptop with audio enhancements off (measured; target 95% not met)` |
| RAM daemon | ≤256 MB | process measurement | `docs/metrics.json` (`resources_idle`) | MEASURED: working set 53,5 MB idle, puncak 55,8 MB; private commit 295,5 MB | `Daemon working set ≈54 MB (measured)` |
| CPU idle listening | ≤10% | process measurement | `docs/metrics.json` (`resources_idle`) | MEASURED: rata-rata 3,49% satu core (0,44% mesin 8 thread) selama 30 s | `Idle listening: 3.5% of one core (measured)` |

## Change rule
Jika requirement berubah:
1. Ubah PRD/feature requirement.
2. Ubah design dan task terkait.
3. Perbarui baris matriks ini.
4. Perbarui schema/vector bila kontrak berubah.
5. Jalankan ulang verifikasi yang terdampak.
6. Jangan mempertahankan bukti lama untuk versi perilaku baru.