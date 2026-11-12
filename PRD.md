# Product Requirements Document (PRD)

**Project Name:** Apollo-26  
**Tagline:** Acoustic Air-Gap Lunar Guidance Protocol & Telemetry Bridge  
**Competition:** Kiroween 2026 Hackathon (Kiro × Devpost)  
**Track:** Frankenstein Category  
**Document Version:** 2.3.0  
**Status:** Approved for Spec-Driven Development  
**Target Deadline:** December 4, 2026 @ 14:00 PT (December 5, 2026 @ 05:00 WIB)  
**Versi sebelumnya:** [`docs/archive/PRD-v2.0.md`](docs/archive/PRD-v2.0.md)

---

## 0. Changelog

### v2.2 → v2.3
| # | Perubahan | Alasan |
| :-- | :-- | :-- |
| 15 | Runtime trigger `PostFileCreate` diganti menjadi sesi **Flight Watch** yang memanggil `await_telemetry_frame()` | File hook Kiro hanya terpicu ketika agen membuat file, bukan ketika daemon eksternal menulis file. |
| 16 | Frame v1 diperjelas menjadi 34 byte dengan `frame_type`, `seq`, dan `ref_seq` | Frame `AUTH` kini dapat menunjuk secara eksplisit ke sequence perintah yang diotorisasi. |
| 17 | Tambah foundation steering, kontrak mesin-terbaca, state machine, threat model, dan evidence matrix | Mengurangi ambiguitas lintas Python–TypeScript dan mencegah klaim tanpa bukti. |

### v2.1 → v2.2
| # | Perubahan | Alasan |
| :-- | :-- | :-- |
| 12 | Frontend memakai **Next.js + TypeScript + Tailwind** dengan `output: 'export'` (statis), disajikan daemon Python | Struktur komponen lebih rapi dan bisa memakai `magicui` / `react-bits`; juri tetap cukup memasang Python. |
| 13 | Tambah PBT sisi TypeScript dengan `fast-check` (P9) | Encoder frame JS diuji terhadap vektor uji yang sama dengan Python. |
| 14 | Mode 1200 baud dan VERB `V06` / `V16` / `V35` dipotong dari v1 | Menutup tambahan waktu setup Next.js (tangga pemotongan TASK.md §4, anak tangga 2 dan 4). |

### v2.0 → v2.1

| # | Perubahan | Alasan |
| :-- | :-- | :-- |
| 1 | Hook diganti dari event fiktif `acoustic_carrier_detected` ke `PostFileCreate` (+ fallback tool blocking) | Kiro hanya punya trigger event IDE (`PostFileCreate`, `PreToolUse`, dst.). |
| 2 | Audio didengar terus oleh **Acoustic Daemon**, agen membaca frame dari buffer | Agen butuh beberapa detik untuk bangun; burst audio sudah lewat. |
| 3 | Modem FSK Bell-202 ditulis sendiri (NumPy + `sounddevice`) | `fskmodem` hanya pembungkus `minimodem` (Linux/ALSA), tidak jalan di Windows. |
| 4 | Emulator AGC = **subset buatan sendiri** (AGC-faithful), bukan menjalankan Luminary/Colossus | Realistis untuk 3 minggu; Virtual AGC berlisensi GPL v2+, bentrok dengan MIT bila dibundel. |
| 5 | Spec dipecah per fitur: `.kiro/specs/<fitur>/` | Struktur spec bawaan Kiro. |
| 6 | Target latensi dipisah: jalur deterministik vs. jalur agen | Agen LLM + jeda 100 ms/tombol tidak mungkin ≤ 2 detik. |
| 7 | Tambah **HMAC + sequence counter** di setiap frame | CRC hanya mendeteksi kerusakan, bukan pengirim palsu atau replay. |
| 8 | Klaim metrik ditulis ulang secara terukur | "0 dB", "kebal 100%", "100% CRC" tidak bisa dipertahankan di depan juri. |
| 9 | Tambah mode input WAV & loopback | Juri mungkin mencoba tanpa mikrofon atau di ruangan bising. |
| 10 | Aturan keselamatan ditegakkan di **kode** + hook `PreToolUse`, steering hanya panduan | Steering tidak memblokir apa pun secara teknis. |
| 11 | Kode perintah kritis memakai VERB AGC yang nyata (V37, V34) | V97 di v2.0 tidak terverifikasi sebagai "Engine Cut-off". |

---

## 1. Executive Summary & Vision

**Apollo-26** adalah sistem kendali telemetri darurat yang menjahit dua era komputasi yang terpisah 57 tahun:

1. **The Relic (1969):** Arsitektur **Apollo Guidance Computer Block II**: word 15-bit + 1 bit paritas, aritmetika *ones' complement*, dan antarmuka **DSKY** (VERB / NOUN / PROG, register R1–R3, lampu `COMP ACTY`, `UPLINK ACTY`, `KEY REL`, `OPR ERR`).
2. **The Pilot (2026):** Agen AI **Kiro** yang bekerja lewat **Model Context Protocol (MCP)**, *Spec-Driven Development*, *Agent Hooks*, *Steering*, dan *Property-Based Testing*.

Penghubungnya bukan Ethernet, Wi-Fi, atau Bluetooth, melainkan **gelombang suara**: modulasi FSK dengan nada Bell-202 (1200 Hz = bit 1 / *mark*, 2200 Hz = bit 0 / *space*), dari speaker stasiun bumi ke mikrofon wahana.

**Klaim inti (yang bisa dipertahankan):** jalur perintah ke komputer pemandu **tidak memiliki antarmuka IP**. Setiap perintah harus lolos tiga gerbang deterministik (CRC-16, HMAC, sequence counter) dan satu gerbang keselamatan berbasis kode sebelum menyentuh register AGC. Agen Kiro berperan sebagai *Flight Director* yang merencanakan urutan tombol DSKY, tetapi **tidak bisa** melewati gerbang tersebut.

---

## 2. Problem Statement & Impact

### 2.1 Masalah
* **Jalur perintah berbasis IP memperluas permukaan serangan.** Satelit modern makin banyak memakai bus dan protokol jaringan terbuka. Bila ground station atau tautan disusupi, penyerang bisa menyuntikkan perintah propulsi.
* **LLM tanpa batasan berbahaya untuk sistem kendali.** Model bisa berhalusinasi angka register, salah format data, atau menjalankan perintah destruktif.

### 2.2 Solusi
* **Tanpa antarmuka jaringan di jalur perintah:** emulator AGC tidak punya stack TCP/IP; satu-satunya input perintah adalah frame akustik yang sudah tervalidasi.
* **Frame terautentikasi:** CRC-16 untuk integritas, HMAC-SHA256 untuk keaslian pengirim, sequence counter untuk menolak *replay*.
* **Gerbang keselamatan deterministik:** aturan keselamatan diimplementasikan di kode MCP server dan diuji dengan PBT. Agen tidak bisa mengeksekusi perintah kritis tanpa otorisasi operator.

### 2.3 Batasan yang diakui (ditulis juga di README)
* Kanal akustik bisa disadap dan diganggu (*jamming*) oleh siapa pun di dekatnya. HMAC mencegah pemalsuan, bukan penyadapan; payload tidak dienkripsi di v1.
* Kiro Agent memakai LLM di cloud. Klaim "offline" berlaku untuk **jalur perintah** (daemon, MCP server, emulator AGC), bukan untuk laptop secara keseluruhan.
* Ini demonstrasi konsep di atas emulator, bukan sistem *flight-certified*.

### 2.4 Metrik Dampak (terukur)
| Metrik | Target | Cara membuktikan |
| :-- | :-- | :-- |
| Antarmuka IP di jalur perintah | 0 | Daemon & MCP server hanya bind ke `127.0.0.1`; tes memastikan tidak ada socket keluar. |
| Frame korup/palsu yang dieksekusi | 0 dari seluruh kasus PBT | PBT bit-flip, noise, dan pemalsuan HMAC (§9). |
| Waktu triase perintah darurat | ≤ 10 detik (vs. ±20 menit hitung manual) | Diukur di demo: nada pertama → DSKY ter-update via agen. |

---

## 3. Arsitektur Sistem

```
┌───────────────────────────────────────────────┐
│ GROUND STATION (browser / HP)                 │
│ web-dashboard → route /ground (Next.js statis)│
│ - Komposer perintah VERB/NOUN/PROG/ΔV         │
│ - Encoder frame + CRC-16 + HMAC (JS)          │
│ - Modulator FSK Bell-202 (Web Audio API)      │
└──────────────────────┬────────────────────────┘
                       │  (((( suara di udara ))))
┌──────────────────────▼────────────────────────┐
│ ACOUSTIC DAEMON (Python, 127.0.0.1 only)      │
│ - Capture mikrofon terus-menerus (sounddevice)│
│ - Deteksi preamble 1200 Hz ≥ 250 ms           │
│ - Demodulator FSK (Goertzel) → byte           │
│ - Validasi CRC-16 → HMAC → sequence           │
│ - Frame valid  → telemetry/inbox/*.json       │
│ - Frame ditolak → telemetry/rejected/*.json   │
│ - Emulator AGC + DSKY (agc-core/)             │
│ - WebSocket lokal → Mission Console           │
└──────────┬──────────────────────────▲─────────┘
           │ file baru di inbox       │ localhost RPC
┌──────────▼──────────┐    ┌──────────┴─────────┐
│ KIRO FLIGHT WATCH   │◄──►│ MCP SERVER (stdio) │
│ await_telemetry_    │MCP │ mcp-server/        │
│ frame() + Specs     │    │ Safety gate (kode) │
└─────────────────────┘    └────────────────────┘
                       ▲
┌──────────────────────┴────────────────────────┐
│ MISSION CONSOLE (route /console, localhost)   │
│ DSKY live, spektrogram dari mikrofon asli,    │
│ log audit frame, status hook & safety gate    │
└───────────────────────────────────────────────┘
```

### 3.1 Komponen
| Komponen | Teknologi | Tanggung jawab |
| :-- | :-- | :-- |
| Ground Station | Next.js (route `/ground`), Web Audio API, Web Crypto (HMAC-SHA256) | Menyusun & memancarkan frame. Bisa dibuka di HP lewat HTTPS (GitHub Pages). |
| Acoustic Daemon | Python 3.12+, NumPy, `sounddevice` | Mendengar, mendekode, memvalidasi, menyimpan frame; menjalankan emulator AGC; menyajikan hasil build frontend. |
| AGC Core | Python murni | Emulator subset AGC Block II + logika DSKY. |
| MCP Server | MCP Python SDK, transport stdio | Tool untuk agen; menegakkan safety gate. |
| Mission Console | Next.js (route `/console`), WebSocket ke daemon | Visualisasi live untuk operator dan video demo. |

**Aturan frontend:**
* Next.js dengan `output: 'export'`. Tidak ada API routes, SSR, server actions, atau middleware.
* Hasil build (`web-dashboard/out/`) disajikan daemon Python di `127.0.0.1`. Juri tidak perlu Node.js; Node.js LTS hanya untuk development.
* Semua data live datang dari daemon lewat WebSocket lokal.

### 3.2 Emulator AGC (subset, "AGC-faithful")
Yang **diemulasikan dengan setia**:
* Word 15-bit + bit paritas ganjil, aritmetika *ones' complement* (termasuk −0), overflow.
* Memori erasable 2048 word; register A, L, Q, Z.
* Siklus input DSKY: `VERB`, `NOUN`, `0–9`, `+`, `−`, `ENTR`, `PRO`, `CLR`, `RSET`, `KEY REL`; lampu `OPR ERR` untuk input tidak valid.
* Jeda minimal 100 ms antar tombol (FR-10).

Yang **disederhanakan** (dan dinyatakan jujur di README):
* Tidak menjalankan Luminary 99 / Colossus 249 asli. Program yang tersedia: `P00` (idle), `P40` (burn SPS, versi sederhana).
* Subset VERB yang didukung: `V25` (muat 3 komponen ke R1–R3), `V34` (terminasi), `V37` (ganti program). `V06`, `V16`, `V35` dipotong dari v1.
* Makna VERB/NOUN dicocokkan dengan dokumentasi Virtual AGC sebelum rilis.

Stretch goal (hanya bila waktu tersisa): adapter opsional ke `yaAGC` sebagai proses terpisah, tidak dibundel di repo.

---

## 4. Protokol Akustik

### 4.1 Lapisan fisik
* Nada Bell-202: mark 1200 Hz (bit 1), space 2200 Hz (bit 0), fase kontinu.
* Baud rate: **300 baud** (satu-satunya mode di v1; 1200 baud dipotong).
* Framing byte: asinkron 8N1 (1 start bit, 8 data bit LSB-first, 1 stop bit).
* Preamble: nada mark kontinu ≥ 250 ms, lalu sync word.
* Sample rate: 48 kHz (fallback 44,1 kHz).

### 4.2 Format frame v1 (34 byte)
| Offset | Field | Tipe | Keterangan |
| :-- | :-- | :-- | :-- |
| 0 | `sync` | 2 byte | `0xA5 0x26` |
| 2 | `version` | uint8 | `0x01` |
| 3 | `frame_type` | uint8 | `0x01` = `COMMAND`, `0x02` = `AUTH` |
| 4 | `seq` | uint32 BE | Sequence global; harus lebih besar dari frame terakhir yang diterima |
| 8 | `ref_seq` | uint32 BE | `0` untuk `COMMAND`; target command sequence untuk `AUTH` |
| 12 | `flags` | uint8 | bit0 = `CRITICAL`; bit lain wajib `0` di v1 |
| 13 | `verb` | uint8 | 0–99; `0` untuk `AUTH` |
| 14 | `noun` | uint8 | 0–99; `0` untuk `AUTH` bila tidak relevan |
| 15 | `program` | uint8 | 0–99; `0` untuk `AUTH` |
| 16 | `r1` | int16 BE | Azimuth, satuan 0,01° |
| 18 | `r2` | int16 BE | Elevasi, satuan 0,01° |
| 20 | `delta_v` | int32 BE | ΔV, satuan 0,1 ft/s (fixed-point, tanpa float) |
| 24 | `hmac` | 8 byte | HMAC-SHA256 dipotong 64-bit, dihitung atas byte 2–23 |
| 32 | `crc` | uint16 BE | CRC-16/CCITT-FALSE atas byte 2–31 |

`COMMAND` ditandatangani `APOLLO26_LINK_KEY`; `AUTH` ditandatangani `APOLLO26_OPERATOR_KEY`. Detail normatif dan vektor uji ada di [`contracts/acoustic-frame-v1.md`](contracts/acoustic-frame-v1.md).

Durasi transmisi pada 300 baud (8N1): 34 byte × 10 bit ÷ 300 ≈ 1,13 detik + preamble 0,25 detik ≈ **1,38 detik**.

### 4.3 Urutan validasi (deterministik, tanpa LLM)
1. Sync word cocok.
2. CRC-16 valid.
3. HMAC valid (kunci bersama dari variabel lingkungan `APOLLO26_LINK_KEY`; contoh kunci demo ada di `.env.example`, kunci asli tidak pernah di-commit).
4. `seq` > `seq` terakhir yang diterima (anti-replay).
5. Rentang field valid (VERB/NOUN/PROG 0–99, ΔV dalam batas yang ditetapkan di steering).

Frame yang gagal di langkah mana pun ditulis ke `telemetry/rejected/` beserta alasannya, lalu dibuang tanpa menghentikan daemon.

---

## 5. Functional Requirements (EARS)

### 5.1 Tautan akustik
* **FR-1 (Event-driven):** WHEN daemon mendeteksi nada 1200 Hz kontinu selama ≥ 250 ms, THE daemon SHALL mulai mendemodulasi frame dan menyalakan lampu `UPLINK ACTY`.
* **FR-2 (Unwanted behavior):** IF sebuah frame gagal salah satu langkah validasi §4.3, THEN THE daemon SHALL membuang frame tersebut, mencatat alasannya ke `telemetry/rejected/`, dan tetap berjalan.
* **FR-3 (Ubiquitous):** THE daemon SHALL menulis setiap frame valid sebagai satu file JSON baru di `telemetry/inbox/`.
* **FR-4 (Unwanted behavior):** IF frekuensi nada terdeteksi menyimpang lebih dari 50 Hz dari 1200/2200 Hz, THEN THE daemon SHALL mencatatnya sebagai anomali telemetri.
* **FR-5 (Optional feature):** WHERE mode `--input <file.wav>` atau `--loopback` aktif, THE daemon SHALL memproses audio dari sumber tersebut dengan pipeline yang sama seperti mikrofon.

### 5.2 Agen Kiro & MCP
* **FR-6 (Event-driven):** WHEN operator memulai sesi Flight Watch, THE agen SHALL memanggil `await_telemetry_frame(timeout_sec)` dan menunggu frame valid dari daemon melalui MCP.
* **FR-7 (Event-driven):** WHEN `await_telemetry_frame` mengembalikan frame, THE agen SHALL memanggil `inspect_agc_status()` sebelum menyusun urutan tombol DSKY.
* **FR-8 (Ubiquitous):** THE MCP server SHALL memvalidasi setiap panggilan `execute_dsky_sequence` terhadap aturan keselamatan di kode (`safety_gate.py`), terlepas dari apa pun yang diputuskan agen.
* **FR-9 (Unwanted behavior):** IF urutan tombol berisi perintah kritis (§7.3), THEN THE MCP server SHALL menolak eksekusi sampai frame `AUTH` operator yang valid untuk `seq` tersebut diterima.

### 5.3 Emulator AGC & DSKY
* **FR-10 (Ubiquitous):** THE emulator SHALL memproses penekanan tombol DSKY dengan jeda minimal 100 ms dan hanya ketika `KEY REL` tidak menyala.
* **FR-11 (State-driven):** WHILE `P40` aktif, THE emulator SHALL menampilkan R1 (azimuth), R2 (elevasi), R3 (ΔV) dan menyalakan `COMP ACTY` secara berkala.
* **FR-12 (Unwanted behavior):** IF urutan tombol tidak valid menurut logika DSKY, THEN THE emulator SHALL menyalakan `OPR ERR` dan tidak mengubah state program.

---

## 6. Non-Functional Requirements

| Parameter | Target | Keterangan |
| :-- | :-- | :-- |
| Latensi jalur deterministik | ≤ 2,0 detik | Nada pertama → frame valid tersimpan di inbox (300 baud). |
| Latensi jalur penuh via agen | ≤ 10 detik | Nada pertama → register DSKY ter-update. |
| Isolasi jaringan jalur perintah | 0 socket ke luar `127.0.0.1` | Berlaku untuk daemon, MCP server, emulator. |
| Keandalan dekode | ≥ 95% frame valid pada jarak speaker–mikrofon 0,5 m di ruangan biasa | Diukur dan dilaporkan apa adanya di README. |
| Resource | RAM ≤ 256 MB, CPU ≤ 10% saat idle mendengar | Diukur di laptop development. |
| Platform | Windows 10/11 (utama), macOS/Linux (best effort) | Laptop development memakai Windows. |
| Prasyarat juri | Python 3.12+, browser modern | Tidak perlu Node.js. |
| Prasyarat development | + Node.js LTS | Python dan Node.js belum terpasang di laptop development. |

---

## 7. Integrasi Fitur Kiro

### 7.1 MCP Server (`mcp-server/`)
| Tool | Fungsi |
| :-- | :-- |
| `read_telemetry_frames(since_seq?)` | Membaca frame valid dari inbox (sudah lolos CRC/HMAC/seq). |
| `await_telemetry_frame(timeout_sec)` | Menunggu frame baru dalam sesi Flight Watch; ini jalur runtime resmi. |
| `inspect_agc_status()` | Membaca register, program aktif, dan status lampu DSKY. |
| `plan_dsky_sequence(frame_seq)` | Mengubah frame menjadi urutan tombol kanonik secara deterministik (agen bisa membandingkan rencananya). |
| `execute_dsky_sequence(keys, frame_seq)` | Mengirim tombol ke emulator **setelah** lolos `safety_gate`. |
| `verify_crc16(hex_payload)` | Utilitas verifikasi CRC untuk audit. |

### 7.2 Agent Hooks (`.kiro/hooks/`)
| Hook | Trigger | Aksi |
| :-- | :-- | :-- |
| `flight-mode-shell-guard` | `PreToolUse`, matcher kategori `shell` | Blokir (exit 2) hanya bila file `telemetry/FLIGHT_MODE` ada. |
| `test-after-spec-task` | `PostTaskExec` | Jalankan validasi yang terkait setelah tugas spec selesai. |
| `pbt-on-save` | `PostFileSave`, matcher `(mcp-server|agc-core|acoustic)[\\/].*\.py$` | Jalankan profil tes cepat saat agen menyimpan kode Python. |

`PostFileCreate` **tidak dipakai sebagai event bus runtime** karena hook file Kiro hanya terpicu oleh file yang dibuat agen. Operator memulai sesi Flight Watch, lalu agen menunggu frame melalui `await_telemetry_frame()`.

### 7.3 Steering (`.kiro/steering/`)
* `product.md`: ringkasan produk & batasan klaim.
* `tech.md`: stack, cara build/test, konvensi kode.
* `structure.md`: batas modul, arah dependency, dan sumber kebenaran state.
* `agc-safety-rules.md`: aturan untuk agen, **dicerminkan** oleh `safety_gate.py`:
  1. Hanya memakai tool MCP Apollo-26 saat memproses frame.
  2. Tidak menjalankan shell saat flight mode aktif (ditegakkan hook `flight-mode-shell-guard`).
  3. Wajib memanggil `inspect_agc_status()` dan memastikan `KEY REL` padam sebelum mengirim tombol.
  4. Perintah kritis yang wajib frame `AUTH` operator:
     * `V37` (ganti program) saat `P40` aktif.
     * `V34` (terminasi) saat `P40` aktif.
     * Eksekusi `P40` dengan |ΔV| di atas ambang yang ditetapkan.
  5. Anomali frekuensi > 50 Hz wajib disebutkan di laporan agen.

* `design-system.md`: steering `fileMatch` untuk `web-dashboard/**`, dibuat sebelum M5 dari §8.

### 7.4 Specs (`.kiro/specs/`)

| Spec | Isi |
| :-- | :-- |
| `acoustic-link/` | Modem FSK, format frame, validasi, daemon. |
| `agc-emulator/` | Word 15-bit, DSKY, P00/P40. |
| `mcp-bridge/` | Tool MCP, safety gate, hook. |
| `mission-console/` | Ground station & Mission Console. |

Masing-masing berisi `requirements.md` (EARS), `design.md`, dan `tasks.md`.

### 7.5 Kiro Powers (stretch goal)
Mengemas MCP server + steering `agc-safety-rules.md` sebagai satu Kiro Power agar bisa dipasang ulang dengan satu langkah.

---

## 8. Design System (Mission Console & Ground Station)

**Diubah 12 Nov 2026 (keputusan operator):** gaya visual mengikuti mockup dashboard yang diarsipkan (`docs/archive/mockups/dashboard-page.html`, tema "Console": graphite, grotesk sans, aksen amber). Token dan aturan lengkap: `.kiro/steering/design-system.md`. Angka contoh, keypad, dan verb di luar cakupan dari mockup tidak dipakai.

* **Warna:** paper/ink graphite, aksen amber, biru (info), hijau (diterima/live), merah (ditolak/gagal); nilai oklch di steering.
* **Tipografi:** *Host Grotesk* (UI dan judul), *Atkinson Hyperlegible Mono* (telemetri).
* **Bentuk:** kartu 8px, kontrol 6px, tag 4px; border 1px.
* Gaya sebelumnya (Celestial Brutalism: Cosmic Void, Lunar Titanium, Electrum Gold, DSKY Phosphor; Italiana/Syne/Space Mono) tidak dipakai lagi.
* **Interaksi:**
  * Spektrogram dan waterfall dari **audio mikrofon asli** yang dialirkan daemon, bukan pola sintetis.
  * Bit yang dipancarkan ground station adalah **hasil encoding frame sebenarnya**.
  * Tombol PBT di console menampilkan hasil `pytest` terakhir yang benar-benar dijalankan, bukan animasi.
  * DSKY dengan klik membran 900 Hz dan lampu yang mengikuti state emulator.
* **Stack UI:** Tailwind untuk token desain; komponen `magicui` / `react-bits` dipakai secukupnya dan hanya yang berjalan di client component.
* **Sumber aturan desain:** `.kiro/steering/design-system.md` (format `design.md`, `inclusion: fileMatch` untuk `web-dashboard/**`).
* **Ruang lingkup UI v1:** Jembatan Akustik, Log Audit Frame, Kontrak & Hook Kiro, Hasil PBT. Storyboard video dan pratinjau responsif **bukan** bagian aplikasi.

---

## 9. Property-Based Testing (Hypothesis)

| # | Properti | Level | Jumlah kasus |
| :-- | :-- | :-- | :-- |
| P1 | `decode(encode(frame)) == frame` untuk semua frame valid | Byte | 10.000 |
| P2 | Modulasi → demodulasi audio bersih mengembalikan frame identik | Audio | 500 |
| P3 | Sama seperti P2 dengan derau putih pada SNR ≥ 15 dB | Audio | 300 |
| P4 | Setiap bit-flip tunggal/ganda pada frame → ditolak | Byte | 10.000 |
| P5 | Audio acak (derau, nada liar, klik) tidak pernah menghasilkan frame yang lolos | Audio | 1.000 |
| P6 | Frame dengan HMAC salah atau `seq` lama → ditolak | Byte | 10.000 |
| P7 | Untuk sembarang state AGC dan urutan tombol, perintah kritis tanpa `AUTH` tidak pernah dieksekusi | Safety gate | 10.000 |
| P8 | Aritmetika *ones' complement* 15-bit: `x + (−x) = −0`, komutatif, overflow konsisten | AGC | 10.000 |
| P9 | Encoder frame TypeScript identik dengan vektor uji Python, dan `decode(encode(x)) == x` di sisi TS (`fast-check`) | Byte (TS) | 10.000 |

Profil `pytest` ringan (≈ 100 kasus/properti) dipakai di hook `pbt-on-save`; profil penuh dijalankan sebelum rilis dan hasilnya disimpan di `docs/pbt-report.md`.

---

## 10. Struktur Repositori

```text
apollo-26/
├── .kiro/                        # WAJIB, tidak boleh di-.gitignore
│   ├── specs/
│   │   ├── acoustic-link/        # requirements.md, design.md, tasks.md
│   │   ├── agc-emulator/
│   │   ├── mcp-bridge/
│   │   └── mission-console/
│   ├── steering/
│   │   ├── product.md
│   │   ├── tech.md
│   │   ├── structure.md
│   │   ├── agc-safety-rules.md
│   │   └── design-system.md
│   ├── hooks/
│   │   ├── flight-mode-shell-guard.json
│   │   ├── test-after-spec-task.json
│   │   └── pbt-on-save.json
│   └── settings/mcp.json         # registrasi MCP server lokal
├── acoustic/                     # Daemon & modem
│   ├── modem.py                  # Modulator/demodulator Bell-202
│   ├── frame.py                  # Encode/decode frame, CRC, HMAC
│   └── daemon.py                 # Capture mic, inbox writer, WebSocket lokal
├── agc-core/
│   ├── word.py                   # Word 15-bit ones' complement + paritas
│   ├── agc_engine.py             # Register & memori erasable
│   └── dsky.py                   # Logika DSKY, P00/P40
├── mcp-server/
│   ├── server.py                 # Tool MCP (stdio)
│   └── safety_gate.py            # Penegakan aturan keselamatan
├── web-dashboard/                # Next.js + TS + Tailwind, output: 'export'
│   ├── app/
│   │   ├── ground/page.tsx       # Ground station (bisa dibuka di HP)
│   │   └── console/page.tsx      # Mission Console
│   ├── lib/frame.ts              # Encoder frame + CRC + HMAC (TS)
│   ├── tests/                    # fast-check (P9)
│   ├── public/sample_burst.wav   # Contoh frame untuk juri tanpa mikrofon
│   └── out/                      # Hasil build statis, disajikan daemon
├── tests/                        # PBT Hypothesis (P1–P8)
├── telemetry/                    # inbox/, rejected/ (isi di-.gitignore, folder tetap)
├── contracts/
│   ├── acoustic-frame-v1.md       # Kontrak biner normatif
│   ├── telemetry-frame.schema.json
│   ├── websocket-events.schema.json
│   └── vectors/                   # Golden vectors Python ↔ TypeScript
├── docs/
│   ├── state-machines.md
│   ├── threat-model.md
│   ├── evidence-matrix.md
│   └── archive/PRD-v2.0.md
├── .env.example                  # Kunci HMAC demo
├── LICENSE                       # MIT
├── PRD.md
└── README.md
```

---

## 11. Penyelarasan Kriteria Juri

* **Potential Impact:** jalur perintah tanpa antarmuka IP, dengan autentikasi frame dan gerbang keselamatan yang terbukti lewat PBT. Batasan ditulis jujur.
* **Technological Implementation:** 4 spec EARS, 3 hook (`PreToolUse`, `PostTaskExec`, `PostFileSave`), 5 steering terfokus, custom MCP server, kontrak lintas bahasa, dan 9 properti PBT (Hypothesis + fast-check).
* **Design:** Mission Console bergaya dashboard "Console" (mockup) dengan data live (mikrofon asli, state emulator asli).
* **Innovation:** komputer pendarat Bulan 1969 dan agen AI 2026 yang hanya berkomunikasi lewat suara.
* **Presentation:** video ≤ 3 menit dengan dua perangkat terpisah (HP sebagai ground station, laptop sebagai wahana).

### Alur video (180 detik)
| Waktu | Adegan |
| :-- | :-- |
| 0:00–0:20 | Masalah: perintah satelit lewat jaringan bisa disusupi. |
| 0:20–0:40 | Konsep: 1969 × 2026 lewat suara. |
| 0:40–1:20 | Demo utama: HP memancarkan frame → spektrogram live → Flight Watch menerima frame lewat MCP → DSKY P40 ter-update. |
| 1:20–1:50 | Demo keselamatan: frame palsu ditolak (HMAC), `V37` saat burn diblokir sampai frame `AUTH` operator. |
| 1:50–2:20 | Kiro di balik layar: spec EARS, steering, hook, hasil PBT. |
| 2:20–3:00 | Metrik terukur, batasan, dan ajakan mencoba repo. |

---

## 12. Rencana Pelaksanaan (12 Nov – 4 Des 2026)

| Milestone | Tanggal | Hasil | Kriteria selesai |
| :-- | :-- | :-- | :-- |
| M0 Persiapan | 12–13 Nov | Python/Node terpasang, repo publik + MIT, 4 steering foundation, kontrak dan assurance docs | Runtime tersedia; JSON contracts valid; repo publik dengan lisensi terdeteksi |
| M1 Spike risiko | 13–14 Nov | Uji nada 1200/2200 Hz HP → mic laptop | SNR/deviasi dicatat; keputusan jarak demo masuk `design.md` |
| M2 Acoustic Link | 14–19 Nov | Modem, frame, daemon, P1–P6 | Frame dari HP terdekode di laptop |
| M3 AGC Emulator | 19–23 Nov | Word 15-bit, DSKY, P00/P40, P8 | Urutan `V37 E 40 E` → P40 aktif di emulator |
| M4 MCP Bridge | 23–27 Nov | Tool MCP, safety gate, 3 hook, P7 | Alur penuh suara → agen → DSKY berjalan |
| M5 Console & Ground Station | 27 Nov–1 Des | UI live, WAV sample | Semua panel menampilkan data asli |
| M6 Video & Submisi | 1–4 Des | Video YouTube publik, README, Devpost | Submisi terkirim sebelum 4 Des 14:00 PT |
| Bonus | setelah submisi | Blog, pos `#KiroweenHackathon26` | Opsional |

**Prinsip:** tidak ada fitur atau mockup baru sebelum alur utama (suara → frame valid → agen → DSKY) terbukti berjalan.
