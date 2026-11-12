---
inclusion: always
---

# Apollo-26 Product Context

## Tujuan
Apollo-26 mendemonstrasikan jalur perintah darurat tanpa antarmuka IP: ground station memancarkan frame Bell-202 lewat suara, daemon memvalidasinya, agen Kiro merencanakan input DSKY melalui MCP, dan emulator AGC subset mengeksekusinya.

## Skenario utama
HP memancarkan `COMMAND` terautentikasi → mikrofon laptop → daemon → sesi Kiro Flight Watch → MCP safety gate → DSKY P40.

## Prioritas keputusan
1. Keselamatan dan kebenaran protokol.
2. Alur end-to-end yang nyata dan dapat diulang.
3. Bukti penggunaan Kiro (Specs, Steering, Hooks, MCP, PBT).
4. UI dan presentasi.

## Klaim yang boleh dibuat
- Jalur perintah daemon–MCP–AGC tidak memiliki socket keluar dari `127.0.0.1` setelah diverifikasi.
- Frame memakai CRC-16 untuk integritas, HMAC-SHA256 terpotong untuk autentikasi demo, dan sequence counter untuk anti-replay.
- Angka performa hanya boleh disebut sebagai `target`, `measured`, atau `verified` sesuai `docs/evidence-matrix.md`.
- Emulator adalah subset AGC-faithful, bukan AGC flight software asli.

## Klaim yang dilarang
Jangan menulis “kebal 100%”, “bebas exploit”, “100% CRC”, “0 dB attack surface”, “100% offline”, atau angka hasil pengujian yang belum diukur. Kiro menggunakan LLM cloud; klaim offline hanya berlaku pada jalur perintah lokal.

## Batas lingkup v1
- 300 baud saja.
- Program P00 dan P40 sederhana.
- VERB V25, V34, dan V37 saja.
- Tidak menjalankan Luminary 99 atau Colossus 249.
- Landing page di `/` diizinkan operator pada 12 Nov 2026 walau alur suara HP → laptop belum berhasil. Syaratnya: status ditulis jujur di hero dan FAQ, dan semua angka dibaca dari `docs/metrics.json` / `docs/test-summary.json`, termasuk target yang meleset.

Sumber kebenaran produk: `PRD.md`. Jadwal dan keputusan: `TASK.md`.