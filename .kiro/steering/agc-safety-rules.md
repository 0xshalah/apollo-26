---
inclusion: always
---

# AGC Safety Rules

Steering ini mengarahkan agen. Penegakan normatif tetap berada di `mcp-server/safety_gate.py` dan diverifikasi oleh P7.

## S-01 — Tool boundary
Saat Flight Watch aktif, gunakan hanya tool MCP Apollo-26. Jangan menjalankan shell atau mengubah file proyek. Hook `flight-mode-shell-guard` menjadi lapisan tambahan.

## S-02 — Inspect before act
Sebelum `execute_dsky_sequence`, panggil `inspect_agc_status`. Tolak atau tunggu jika `KEY REL` menyala atau state AGC tidak dapat dibaca.

## S-03 — Canonical plan
Panggil `plan_dsky_sequence(frame_seq)` dan bandingkan dengan rencana agen. Eksekusi hanya urutan kanonik untuk frame tersebut.

## S-04 — Critical authorization
Perintah berikut wajib memiliki `AUTH` valid yang `ref_seq`-nya sama dengan sequence `COMMAND`:
- V37 ketika P40 aktif.
- V34 ketika P40 aktif.
- Aktivasi P40 dengan `abs(delta_v)` melewati ambang yang ditetapkan spec `mcp-bridge`.

AUTH harus tervalidasi dengan `APOLLO26_OPERATOR_KEY`, belum pernah dipakai, dan sequence AUTH harus lebih baru dari sequence terakhir.

## S-05 — Key cadence
Kirim tombol hanya ketika `KEY REL` padam, dengan jeda minimal 100 ms. Hentikan urutan jika `OPR ERR` menyala.

## S-06 — Anomaly reporting
Deviasi nada lebih dari 50 Hz adalah anomali yang wajib dilaporkan. Jangan menyebutnya kegagalan CRC kecuali CRC memang gagal. Keputusan menerima/menolak mengikuti kontrak frame dan spec acoustic-link.

## S-07 — No invented evidence
Jangan membuat nilai SNR, latency, CRC rate, PBT count, RAM, atau CPU. Ambil hanya dari tool/status/report. Jika belum ada, tampilkan `UNMEASURED`.