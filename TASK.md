# TASK.md — Apollo-26

Peta kerja tingkat proyek, diturunkan dari [`PRD.md`](PRD.md) v2.1.0.
Tugas implementasi rinci per fitur dibuat lewat **alur Spec Kiro** di `.kiro/specs/<fitur>/tasks.md` pada awal setiap milestone. File ini mengatur urutan, ketergantungan, gerbang, dan apa yang dipotong bila terlambat.

**Deadline keras:** 4 Des 2026, 14:00 PT (5 Des, 05:00 WIB) · **Target submit:** 3 Des 2026
**Prinsip:** tidak ada fitur atau mockup baru sebelum alur utama (suara → frame valid → agen → DSKY) terbukti berjalan.

---

## 1. Ringkasan & Status

| Milestone | Tanggal | Estimasi | Gerbang (harus terbukti) | Status |
| :-- | :-- | --: | :-- | :-- |
| M0 Persiapan & kontrak | 12–13 Nov | 8,5 j | Repo publik + MIT, Python & Node jalan, kontrak terkunci | ✅ repo publik, MIT terdeteksi |
| M1 Spike risiko | 13–14 Nov | 2,75 j | Keputusan hook & kanal akustik tercatat | 🟥 uji speaker→mic laptop sendiri 0/20; uji HP → mic belum; pemicu T1 aktif |
| M2 Acoustic Link | 14–19 Nov | 27,5 j | Frame dari HP masuk `telemetry/inbox/` | 🟨 WAV & loopback 20/20; over-air belum berhasil |
| M3 AGC Emulator | 17–23 Nov | 20,5 j | `V37 E 40 E` → P40 aktif, R1–R3 benar | ✅ (juga di sesi live) |
| M4 MCP Bridge | 23–27 Nov | 21,5 j | Suara → agen → DSKY ≤ 10 detik; serangan ditolak | 🟨 sesi Kiro live lolos (V25 & P40+AUTH); latensi agen 84 s, target 10 s meleset |
| M5 Console (Next.js) | 26 Nov–1 Des | 24,5 j | Semua panel memakai data asli; build statis disajikan daemon | 🟨 tersambung ke daemon nyata (status, DSKY, audit, ringkasan tes); spektrum mic belum terlihat |
| M6 Submisi | 1–3 Des | 16,5 j | Devpost terkirim | ⬜ |
| **Total** | | **≈ 121,75 j** | | |

**Status 12 Nov (akhir hari):** suite Python 132 lulus (termasuk `slow`); profil penuh di `docs/pbt-report.md`; frontend 56 tes + P9 10.000 kasus lulus; sesi Kiro live lolos untuk V25 dan P40+AUTH; metrik di `docs/metrics.json`. Belum: dekode lewat udara, video, Devpost. Rincian bukti: `docs/evidence-matrix.md`.

**Kapasitas:** asumsi 1 orang × ±5 jam efektif/hari × 22 hari ≈ 110 jam. Sekitar 4 jam fondasi dokumentasi sudah selesai; sisa rencana tetap melebihi kapasitas. Tangga pemotongan (§4) adalah bagian dari rencana, bukan rencana darurat.

Legenda: `[ ]` belum · `[x]` selesai · **(R)** berisiko · **⛔** di jalur kritis · `↳` bergantung pada · referensi `FR-x` / `Px` mengacu ke PRD.

---

## 2. Jalur Kritis

```
0.1 Python ─► 1.2 uji nada ─► 2.2 frame ─► 2.4 modem ─► 2.6 daemon ─► 3.8 integrasi ─► 4.4 MCP ─► 4.6 hook ─► 4.9 E2E ─► 6.5 video
3.3 word ─► 3.6 DSKY ─► 3.7 P40 ──────────────────────────────────────┘
```

* M3 (emulator) murni Python tanpa audio, jadi **boleh dimulai paralel** sejak 17 Nov sambil modem di-tuning.
* M5 bergantung pada daemon (WebSocket) dan emulator, bukan pada MCP. Scaffold Next.js (5.2) dan encoder TS (5.3) bisa dikerjakan lebih awal bila M2 macet.

---

## 3. Tugas

Format tiap tugas: **ID · judul** · estimasi · ketergantungan, lalu kriteria selesai yang bisa diverifikasi.

### M0 — Persiapan (12–13 Nov)

- [x] **0.1 ⛔ Pasang Python 3.12+** · 0,5 j
  - `winget install Python.Python.3.12`; selesai bila `python --version` ≥ 3.12 di terminal baru.
- [x] **0.1b Pasang Node.js LTS** · 0,25 j
  - `winget install OpenJS.NodeJS.LTS`; selesai bila `node --version` dan `npm --version` jalan. Hanya untuk development; juri tidak memerlukannya.
- [x] **0.2 Virtual env & dependensi** · 0,5 j · ↳ 0.1
  - `.venv/` + `requirements.txt` (`numpy`, `sounddevice`, `mcp`, `hypothesis`, `pytest`) dengan versi dikunci; `pip install -r requirements.txt` sukses.
- [x] **0.3 Repo GitHub publik** · 0,5 j — <https://github.com/0xshalah/apollo-26>, API GitHub: `public`, lisensi `MIT`
  - `git init`, repo publik `apollo-26`, `LICENSE` MIT; lisensi tampil di bagian *About*.
- [x] **0.4 `.gitignore` aman** · 0,25 j · ↳ 0.3
  - Mengabaikan `.venv/`, `.env`, isi `telemetry/inbox/` & `telemetry/rejected/` (folder tetap via `.gitkeep`). **Tidak** mengabaikan `.kiro/`. Cek: `git check-ignore .kiro` tidak mengeluarkan apa pun.
- [x] **0.5 Kunci demo** · 0,25 j
  - `.env.example` berisi `APOLLO26_LINK_KEY` dan `APOLLO26_OPERATOR_KEY` contoh; `.env` asli tidak ter-commit.
- [x] **0.6 Foundation steering** · 2 j
  - `.kiro/steering/product.md`, `tech.md`, `structure.md`, `agc-safety-rules.md` dibuat; `design-system.md` ditunda sampai M5.
- [x] **0.6a Kontrak & assurance docs** · 4 j
  - `contracts/acoustic-frame-v1.md`, dua JSON Schema, golden vectors, `docs/state-machines.md`, `threat-model.md`, dan `evidence-matrix.md` dibuat.
  - JSON valid secara sintaks; golden vectors masih berstatus independen dan wajib diverifikasi Python + TypeScript.
- [x] **0.7 Commit pertama** · 0,25 j · ↳ 0.3–0.6a — commit `4ff0864`, 12 Nov
  - PRD, TASK, LICENSE, steering ter-push. Ini juga jejak waktu bahwa proyek dimulai setelah 30 Okt 2026.

### M1 — Spike risiko (13–14 Nov)

- [x] **1.1 Keputusan runtime event Kiro** · 0,25 j
  - `PostFileCreate` hanya terpicu ketika agen membuat file, jadi tidak dipakai untuk output daemon.
  - Jalur resmi: operator memulai sesi Flight Watch → agen memanggil `await_telemetry_frame()` melalui MCP.
  - Hooks dipakai untuk guard dan validasi development, bukan sebagai event bus runtime.
- [ ] **1.2 (R) ⛔ Uji kanal akustik HP → laptop** · 2 j · ↳ 0.2
  - HP memutar nada 1200 dan 2200 Hz; laptop merekam 48 kHz; Goertzel membedakan keduanya.
  - Catat SNR dan deviasi Hz pada jarak 0,3 m, 0,5 m, 1 m.
  - Selesai bila: kedua nada terbedakan pada 0,5 m. Bila gagal, lihat pemicu T1 (§4).
- [x] **1.3 Perangkat audio Windows** · 0,5 j · ↳ 0.2 — default input "Microphone Array (Realtek)" dan output "Speakers (Realtek)" mendukung 48 kHz mono (MME)
  - `sounddevice.query_devices()` menampilkan mikrofon; 48 kHz didukung (atau catat fallback 44,1 kHz).

### M2 — Acoustic Link (14–19 Nov) · spec `acoustic-link`

- [x] **2.1 Spec `acoustic-link`** · 3 j · ↳ 1.2
  - Dibuat lewat alur Spec Kiro (requirements EARS → design → tasks) dari PRD §4 dan FR-1–FR-5. Hasil spike 1.2 masuk ke `design.md`.
- [x] **2.2 ⛔ `acoustic/frame.py`** · 3 j · ↳ 2.1
  - Encode/decode frame 34 byte, CRC-16/CCITT-FALSE, HMAC-SHA256 dipotong 8 byte, `COMMAND`/`AUTH`, `seq`/`ref_seq`, validasi urut sesuai kontrak.
  - Verifikasi **vektor uji** di `contracts/vectors/frames.json`; vektor yang sama wajib dipakai encoder TypeScript di 5.3.
- [x] **2.3 PBT P1, P4, P6** · 2 j · ↳ 2.2 — profil penuh 10.000 contoh/properti lulus (`docs/pbt-report.md`)
  - `pytest tests/test_frame.py` lolos dengan profil penuh (10.000 kasus/properti).
- [x] **2.4 ⛔ `acoustic/modem.py`** · 5 j · ↳ 2.2
  - Modulator Bell-202 fase kontinu, 8N1, preamble ≥ 250 ms, 300 baud default; demodulator Goertzel + sinkronisasi bit.
- [x] **2.5 PBT P2, P3, P5** · 3 j · ↳ 2.4 — P2 500, P3 300, P5 1.000 contoh lulus; waktu generate 48 s / 30 s / 5 s (`docs/pbt-report.md`)
  - Lolos dengan jumlah kasus PRD §9; waktu jalan profil penuh dicatat.
- [x] **2.6 ⛔ `acoustic/daemon.py`** · 4 j · ↳ 2.4
  - Capture kontinu dengan buffer cincin; frame valid → `telemetry/inbox/<seq>.json`; ditolak → `telemetry/rejected/` beserta alasan (FR-2, FR-3).
  - Penulisan file **atomik** (tulis ke `.tmp`, lalu rename) agar hook tidak membaca file setengah jadi.
- [x] **2.7 Persistensi `seq`** · 1 j · ↳ 2.6
  - `seq` terakhir disimpan ke disk; restart daemon tidak membuka celah replay.
- [x] **2.8 Anomali frekuensi > 50 Hz** · 1 j · ↳ 2.4 (FR-4)
- [x] **2.9 Mode `--input` dan `--loopback`** · 2 j · ↳ 2.6 (FR-5)
  - Buat `web-dashboard/public/sample_burst.wav`; `python -m acoustic.daemon --input sample_burst.wav` menghasilkan frame di inbox.
- [x] **2.10 Uji isolasi jaringan** · 0,5 j · ↳ 2.6
  - Tes otomatis: semua socket daemon bind ke `127.0.0.1`.
- [ ] **2.11 (R) Tuning di ruangan nyata** · 3 j · ↳ 2.6
  - 20 frame dari HP pada 0,5 m; catat tingkat keberhasilan. Target ≥ 95% (PRD §6).
- **Gerbang M2 (19 Nov):** frame dari HP terdekode benar dan muncul di inbox; P1–P6 hijau. Bila gagal, lihat pemicu T2.

### M3 — AGC Emulator (17–23 Nov) · spec `agc-emulator`

- [ ] **3.1 Verifikasi subset VERB/NOUN** · 1,5 j
  - Cocokkan `V25`, `V34`, `V37` dan NOUN yang dipakai dengan dokumentasi Virtual AGC; tulis tabel + sumber di `design.md`.
- [x] **3.2 Spec `agc-emulator`** · 2 j · ↳ 3.1
  - Alur Spec Kiro dari PRD §3.2 dan FR-10–FR-12.
- [x] **3.3 ⛔ `agc-core/word.py`** · 2 j · ↳ 3.2
  - Word 15-bit, paritas ganjil, ones' complement (termasuk −0), overflow.
- [x] **3.4 PBT P8** · 1 j · ↳ 3.3
- [x] **3.5 `agc-core/agc_engine.py`** · 2 j · ↳ 3.3
  - Memori erasable 2048 word; register A, L, Q, Z.
- [x] **3.6 ⛔ `agc-core/dsky.py`** · 5 j · ↳ 3.5
  - Siklus tombol, lampu `COMP ACTY` / `UPLINK ACTY` / `KEY REL` / `OPR ERR`, jeda ≥ 100 ms, `OPR ERR` untuk urutan tidak valid (FR-10, FR-12).
- [x] **3.7 ⛔ Program P00 & P40** · 4 j · ↳ 3.6
  - R1/R2/R3 diperbarui dan `COMP ACTY` berkedip selama P40 (FR-11).
- [x] **3.8 ⛔ Integrasi ke daemon** · 3 j · ↳ 2.6, 3.7
  - Emulator berjalan di proses daemon; RPC lokal (`127.0.0.1`) untuk MCP server; WebSocket untuk console.
- **Gerbang M3 (23 Nov):** skrip uji menekan `V37 E 40 E`, lalu `V25` + data → P40 aktif dan R1–R3 sesuai input.

### M4 — MCP Bridge & Hooks (23–27 Nov) · spec `mcp-bridge`

- [x] **4.1 Spec `mcp-bridge`** · 2 j · ↳ 3.8
  - Alur Spec Kiro dari PRD §7.1–7.3 dan FR-6–FR-9; Flight Watch + `await_telemetry_frame` menjadi jalur runtime resmi.
- [x] **4.2 ⛔ `mcp-server/safety_gate.py`** · 3 j · ↳ 4.1
  - Perintah kritis (`V37` / `V34` saat P40, |ΔV| > ambang) wajib frame `AUTH` valid untuk `seq` terkait.
- [x] **4.3 PBT P7** · 2 j · ↳ 4.2
- [x] **4.4 ⛔ `mcp-server/server.py`** · 4 j · ↳ 4.2
  - Tool: `read_telemetry_frames`, `await_telemetry_frame`, `inspect_agc_status`, `plan_dsky_sequence`, `execute_dsky_sequence`, `verify_crc16`.
- [x] **4.5 Registrasi MCP** · 1,5 j · ↳ 4.4 — operator memasang `.kiro/settings/mcp.json`; await/inspect/plan/execute/read dipanggil dari sesi Kiro live 12 Nov
  - `.kiro/settings/mcp.json`; tiap tool dipanggil sekali dari chat Kiro dan hasilnya benar.
  - Status 12 Nov: agen tidak diizinkan menulis `.kiro/settings/`. Template siap di `docs/kiro-mcp.json` (execute tidak di-auto-approve, dicek oleh tes). Operator menyalinnya lewat *Kiro: Open workspace MCP config (JSON)*. Server stdio sudah lolos tes `tests/test_mcp_stdio.py`.
- [x] **4.6 ⛔ Hooks** · 2 j · ↳ 4.5
  - Dibuat lewat Kiro: `flight-mode-shell-guard`, `test-after-spec-task`, `pbt-on-save`. Tidak ada hook runtime telemetry.
- [x] **4.7 Uji shell guard** · 1 j · ↳ 4.6
  - Shell diblokir saat `telemetry/FLIGHT_MODE` ada, normal saat tidak ada.
- [ ] **4.8 Prompt agen & steering** · 3 j · ↳ 4.6
  - Uji 10 frame berbeda; agen selalu memanggil `inspect_agc_status` dulu dan rencananya cocok dengan `plan_dsky_sequence`. Perbaiki steering bila menyimpang.
- [ ] **4.9 ⛔ Uji E2E + skenario serangan** · 2 j · ↳ 4.8
  - Skenario: (a) frame sah → DSKY ter-update ≤ 10 detik, (b) frame HMAC palsu → ditolak, (c) replay frame lama → ditolak, (d) `V37` saat P40 tanpa `AUTH` → diblokir, lalu lolos setelah `AUTH`.
- [ ] **4.10 Rekaman cadangan** · 1 j · ↳ 4.9
  - Rekam layar alur E2E apa adanya. Ini jaring pengaman video bila M5–M6 bermasalah.
- **Gerbang M4 (27 Nov):** keempat skenario 4.9 lolos dua kali berturut-turut. Bila gagal, lihat pemicu T3.

### M5 — Mission Console & Ground Station, Next.js (26 Nov–1 Des) · spec `mission-console`

- [ ] **5.0 Steering desain & skill motion** · 1 j
  - `.kiro/steering/design-system.md` dalam format `design.md` dari PRD §8 (token warna, tipografi, aturan Tailwind), `inclusion: fileMatch` untuk `web-dashboard/**`.
  - Baca dulu isi `emilkowalski/skills`, lalu pasang di level user (`~/.kiro/skills/`); hapus setelah proyek selesai.
- [x] **5.1 Spec `mission-console`** · 1,5 j · ↳ 3.8, 5.0
- [x] **5.2 Scaffold Next.js statis** · 4 j · ↳ 0.1b
  - Next.js + TypeScript + Tailwind, `output: 'export'`; tanpa API routes, SSR, server actions, atau middleware.
  - Daemon menyajikan `web-dashboard/out/` di `127.0.0.1`; `/ground` dan `/console` terbuka dari daemon tanpa `next dev`.
- [x] **5.3 `lib/frame.ts` + PBT P9** · 3 j · ↳ 2.2, 5.2
  - Encoder frame + CRC + HMAC (Web Crypto) di TypeScript.
  - `fast-check`: output identik dengan `contracts/vectors/frames.json` dan round-trip lolos 10.000 kasus.
- [x] **5.4 Route `/ground`** · 4 j · ↳ 5.3
  - Komposer perintah dan modulator Web Audio.
  - Bisa mengirim frame **`AUTH` operator**; kunci dimasukkan manual di UI, tidak ditanam di kode.
- [ ] **5.5 GitHub Pages** · 1 j · ↳ 5.4 — situs live di <https://0xshalah.github.io/apollo-26/ground/> (branch `gh-pages`, `scripts/deploy_pages.cmd`, dicek di Chrome headless); belum: bunyi dari HP terdekode daemon
  - `basePath` dikonfigurasi; `/ground` terbuka di HP lewat HTTPS dan bunyinya terdekode daemon.
- [ ] **5.6 Route `/console`** · 7 j · ↳ 3.8, 5.2
  - DSKY live, spektrogram dari mikrofon asli, log audit frame (inbox + rejected), status hook & safety gate, hasil PBT dari `docs/pbt-report.md`.
  - Komponen `magicui` / `react-bits` hanya bila menghemat waktu; semua dalam client component.
- [ ] **5.7 Polish desain** · 3 j · ↳ 5.6
  - Sesuai `design-system.md`; ambil elemen visual yang relevan dari mockup `docs/archive/mockups/` tanpa data palsu. Audit dengan skill hallmark.
- **Gerbang M5 (1 Des):** tidak ada panel yang menampilkan data sintetis atau animasi palsu; build `out/` berjalan dari daemon di clone bersih.

### M6 — Video & Submisi (1–3 Des)

- [x] **6.1 Laporan PBT penuh** · 1 j — `docs/pbt-report.md` dari `scripts/pbt_full.cmd` (132 passed, seed 2026)
  - Hasil disimpan di `docs/pbt-report.md` (jumlah kasus, waktu, seed).
- [x] **6.2 Ukur metrik nyata** · 2 j — `docs/metrics.json` via `scripts/measure_metrics.py`; over-air dan agen meleset target, dicatat apa adanya
  - Latensi deterministik, latensi via agen, keandalan dekode, RAM/CPU; ditulis apa adanya, termasuk yang meleset dari target.
- [x] **6.3 README** · 3 j — quick start, demo P40+AUTH, tabel "Measured so far", screenshot console live; link video masih kosong
  - Konsep, arsitektur, instalasi, mode WAV untuk juri, batasan yang diakui (PRD §2.3), link video.
- [x] **6.4 Uji clone bersih** · 1,5 j · ↳ 6.3 — `scripts/clean_clone_check.cmd` 12 Nov: clone dari GitHub, venv baru, tanpa Node; WAV diterima seq 1, replay ditolak `REPLAY`, `out/console` ada, 125 tes cepat lulus. Tampilan `/console` di clone itu belum dibuka di browser.
  - Clone ke folder baru, ikuti README dari nol **tanpa Node.js**, jalankan mode WAV sampai DSKY ter-update di `/console`. Perbaiki setiap langkah yang macet.
- [ ] **6.5 ⛔ Video ≤ 3 menit** · 6 j · ↳ 4.9
  - Alur PRD §11, dua perangkat, tanpa musik berhak cipta; unggah ke YouTube **publik**; cek durasi < 3:00.
- [ ] **6.6 Audit repo** · 0,5 j
  - Publik, MIT terdeteksi, `.kiro/` lengkap (4 spec, 5 steering, 3 hook, `mcp.json`), tidak ada kunci asli (`git log -p | Select-String APOLLO26_` hanya berisi contoh).
- [ ] **6.7 Naskah Devpost** · 2 j — draf di `docs/devpost.md`; naskah video di `docs/video-script.md`
  - Deskripsi, kategori Frankenstein, *built with*, dan penjelasan penggunaan Kiro yang merujuk file nyata di `.kiro/` dan `docs/kiro-journal.md`.
- [ ] **6.8 ⛔ Submit** · 0,5 j · **paling lambat 3 Des**; sisakan 4 Des sebagai cadangan.

### Sepanjang proyek

- [x] **J.1 Jurnal Kiro** · ±10 menit per milestone — `docs/kiro-journal.md` (tanpa screenshot)
  - Di akhir setiap milestone, tulis 3–5 poin dan 1–2 screenshot di `docs/kiro-journal.md`: spec yang dibuat, hook yang terpicu, PBT yang menangkap bug. Bahan langsung untuk video, Devpost, dan blog.

### Bonus (setelah submisi)

- [ ] **B.1** Artikel blog proses pembuatan dengan Kiro (bahan dari J.1).
- [ ] **B.2** Pos media sosial `#KiroweenHackathon26`.
- [ ] **B.3** (Stretch) Kemas MCP server + steering sebagai Kiro Power.
- [ ] **B.4** (Stretch) Adapter opsional ke `yaAGC` sebagai proses terpisah.

---

## 4. Pengendalian Jadwal

### Pemicu (tripwire)
| ID | Kapan dicek | Kondisi | Tindakan |
| :-- | :-- | :-- | :-- |
| T1 | 14 Nov | Nada tidak terbedakan pada 0,5 m | Coba speaker eksternal / volume penuh / jarak 0,3 m. Bila tetap gagal: demo utama lewat kabel audio, uji lewat udara ditampilkan terpisah. |
| T2 | 19 Nov | Gerbang M2 belum lolos | Bekukan tuning modem, lanjutkan pengembangan memakai mode `--input` WAV; tuning dilanjutkan paralel maksimal 1 jam/hari. |
| T3 | 27 Nov | Gerbang M4 belum lolos | Hentikan polish M5; console cukup DSKY + log audit. Semua waktu ke E2E. |
| T4 | 1 Des | Console belum selesai | Rekam video dengan apa yang sudah jalan; pakai rekaman cadangan 4.10 bila perlu. |

### Tangga pemotongan (potong dari atas bila terlambat)
1. Bonus dan stretch (B.1–B.4).
2. ~~Mode 1200 baud~~ **sudah dipotong 12 Nov** (menutup waktu Next.js).
3. Waterfall spektrogram → diganti batang FFT sederhana.
4. ~~VERB `V06`, `V16`, `V35`~~ **sudah dipotong 12 Nov** (sisa `V25`, `V34`, `V37`).
5. Polish desain 5.7 (pakai gaya dasar dari `design-system.md`).
6. Hook `pbt-on-save`.
7. Ground station di HP → laptop kedua atau speaker laptop yang sama.

**Tidak boleh dipotong:** `.kiro/` (spec, steering, hook utama), HMAC + `seq`, `safety_gate` + P7, alur E2E nyata, mode WAV untuk juri, README, video, lisensi MIT.

---

## 5. Log Keputusan

| Tanggal | Keputusan | Alasan / bukti |
| :-- | :-- | :-- |
| 12 Nov | Emulator AGC subset buatan sendiri | Realistis untuk 3 minggu; Virtual AGC GPL v2+ (PRD §0). |
| 12 Nov | Modem Bell-202 ditulis sendiri | `fskmodem` bergantung pada `minimodem` (Linux). |
| 12 Nov | Frontend Next.js statis (`output: 'export'`) disajikan daemon | Pilihan user; juri tetap cukup Python. Biaya +5 j di M5, ditutup sebagian dengan memotong anak tangga 2 dan 4. |
| 12 Nov | Skill desain: design.md (format), hallmark (audit), emilkowalski/skills (motion); `magicui` / `react-bits` sebagai sumber komponen | Repo lain tumpang tindih, tidak cocok stack, berbayar, atau berlisensi Commons Clause. |
| 12 Nov | Flight Watch + `await_telemetry_frame`, tanpa runtime `PostFileCreate` | Dokumentasi Kiro menyatakan File Create hook hanya terpicu ketika agen membuat file; output daemon eksternal tidak memicu hook. |
| 12 Nov | Jendela inspeksi 5 s → 20 s (catalog v1.0 → v1.1) | Sesi Kiro nyata: jeda antar-panggilan tool agen 5–30 s, sehingga setiap plan selalu `INSPECTION_STALE`. Perubahan state tetap terdeteksi lewat cek revisi AGC di plan, gate, dan daemon. Versi catalog dinaikkan agar pasangan daemon/MCP yang berbeda gagal tertutup dengan `CATALOG_MISMATCH`. |
| 12 Nov | Hold AUTH 30 s → 120 s (catalog v1.2) | Jendela harus mencakup agen melihat HELD, operator manusia mengirim AUTH, lalu await/inspect/plan/execute agen (5–30 s per panggilan); 30 s tidak cukup sehingga perintah kritis selalu `AUTH_EXPIRED`. Kunci operator, ikatan `ref_seq`, sekali pakai, dan urutan sequence tidak berubah. Disetujui operator. |
| 12 Nov | `SystemClock` memakai `perf_counter_ns` dan `sleep_ms` menunggu sampai tenggat | Run live pertama gagal di tombol 2/29 (`KEY_REJECTED`): di Python 3.12 Windows `time.monotonic` = GetTickCount64 (resolusi 15,625 ms), 10 dari 40 `sleep(100 ms)` terukur 93–94 ms. Batas 100 ms tidak diubah. Regresi: `tests/test_system_clock.py`. Run ulang: EXECUTED 29/29, R1/R2/R3 = 1250/420/3120. |
| 12 Nov | Tes live P40 kritis lolos | COMMAND seq 2 (V37 P40, dv 312,0 ft/s) HELD; execute tanpa AUTH ditolak `AUTH_REQUIRED`; AUTH seq 3 MATCHED; EXECUTED 36/36, P40 aktif, R1/R2/R3 = 1250/420/3120. 84,2 s dari COMMAND diterima sampai execute selesai (satu run, termasuk tes negatif). Daemon harus dijalankan di terminal operator: terminal background Kiro menutup proses di antara giliran. |
| 12 Nov | Frame v1 menjadi 34 byte | `frame_type` dan `ref_seq` menghilangkan ambiguitas AUTH; HMAC 64-bit eksplisit untuk demo. |
| 12 Nov | Landing page dipoles satu oktaf | Hero menjadi mission briefing setinggi viewport dengan grid/orbit statis; live P40 card punya packet bytes, mini-DSKY, gate timeline, dan hasil nyata; section memakai label 01–06, evidence utama menjadi kartu, dan ada closing CTA. Semua nilai tetap berasal dari report build-time; lint, typecheck, 65 tes, build, font/CDN/claim scan lulus; dicek pada 1440×1100 dan 375×1100. |
| 12 Nov | Landing page di `/` mengikuti mockup landing | Operator meminta landing page walau alur suara HP belum berhasil; aturan "tidak ada landing sebelum alur utama selesai" di `product.md` diganti syarat kejujuran. Semua angka dibaca saat build dari `docs/metrics.json` dan `docs/test-summary.json` (`lib/landing-data.ts`, dites); target yang meleset tampil FAILED. Bahasa Inggris. |
| 12 Nov | Gaya visual mockup dashboard dipakai sepenuhnya (menggantikan gaya PRD) | Operator memilih opsi B setelah melihat hasil tata letak: palet graphite/amber/biru/hijau/merah (oklch), Host Grotesk + Atkinson Hyperlegible Mono via `next/font`, sudut 8/6/4 px. Aturan kejujuran data tetap: tanpa angka contoh mockup, keypad, atau Verb 97. Aturan desain diperbarui di `.kiro/steering/design-system.md`. |
| 12 Nov | Tata letak ala mockup dashboard, gaya visual tetap PRD | Sidebar bernomor, strip KPI, tabel audit dengan filter dan pencarian, dock DSKY kanan. KPI hanya dari frame yang benar-benar diterima; tidak ada angka mockup, keypad DSKY, atau Verb 97. Daemon kini juga mengirim ulang frame yang ditolak saat console tersambung. Disetujui operator. |
| 12 Nov | Gunakan gaya visual PRD, bukan palet mockup lama | Cosmic Void + Lunar Titanium + Apollo Electrum Gold + DSKY Phosphor lebih autentik dan khas; Italiana hanya untuk judul besar, Syne untuk UI, Space Mono untuk telemetri. |
| 12 Nov | Uji akustik speaker → mic laptop yang sama gagal (0/20) | `scripts/measure_metrics.py`: 20 frame dari speaker Realtek, mic array Realtek, tidak ada yang terdeteksi. Rekaman probe: energi pita 1100–1300 Hz hanya 0,5–1% dan 2100–2300 Hz 0,1–0,2% dari total; energi dominan 170–850 Hz. Tidak terdekode pada ambang amplitudo 0,05 sampai 0,002. Dugaan: pemrosesan suara (array/SST) pada mic laptop menekan nada stabil; belum dibuktikan. Pemicu T1 aktif: uji HP → laptop, matikan *audio enhancements*, atau mic eksternal. Jalur loopback tetap 20/20. |
| _14 Nov_ | _Jarak & volume demo akustik_ | _diisi dari hasil 1.2_ |
