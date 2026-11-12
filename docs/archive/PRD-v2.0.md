# Product Requirements Document (PRD)

**Project Name:** Apollo-26  
**Tagline:** Acoustic Air-Gap Lunar Guidance Protocol & Telemetry Bridge  
**Competition:** Kiroween 2026 Hackathon (Sponsored by AWS & Devpost)  
**Track:** Frankenstein Category  
**Document Version:** 2.0.0 (Grand Prix Edition)  
**Status:** Approved for Spec-Driven Development  
**Target Deadline:** December 4, 2026 @ 14:00 PT (December 5, 2026 @ 05:00 WIB)  

---

## 1. Executive Summary & Vision

**Apollo-26** adalah sistem kendali telemetri antariksa otonom berkeamanan tingkat tinggi yang menyatukan dua era komputasi yang terpisah 57 tahun:
1. **The Vintage Beast (1969):** Logika arsitektur memori ferit (*core rope*) 15-bit dari **Apollo Guidance Computer (AGC Block II)** beserta antarmuka digital **DSKY (Display and Keyboard)** yang memandu pendaratan Apollo 11 di Bulan.
2. **The Autonomous Mind (2026):** Lingkungan rekayasa agen AI **Kiro** (AWS Kiro Agentic IDE), yang beroperasi melalui **Model Context Protocol (MCP)**, *Spec-Driven Development* (SDD), *Event-Driven Agent Hooks*, dan *Property-Based Testing* (PBT).

Jembatan penghubung kedua sistem ini bukanlah kabel data Ethernet, Bluetooth, atau protokol IP modern, melainkan **Acoustic Air-Gap**: gelombang suara analog frekuensi ganda (*Frequency-Shift Keying / FSK* Bell-202 pada nada 1200 Hz dan 2200 Hz).

Dengan memutus total lapisan jaringan fisik dan IP, wahana antariksa kebal 100% terhadap serangan siber jaringan (*zero-day remote exploit*). Setiap instruksi manuver orbital darurat ditransmisikan murni melalui getaran suara speaker ke mikrofon, diuraikan oleh Kiro Agent melalui server MCP, divalidasi dengan aturan EARS formal, dan dieksekusi langsung ke register memori Apollo 1969.

---

## 2. Problem Statement & Impact ($100k Winning Strategy)

### 2.1 Krisis Keamanan Telemetri Antariksa Modern
* **Celah Serangan Berbasis IP:** Satelit dan wahana antariksa modern semakin banyak mengadopsi tumpukan jaringan IP (*Ethernet bus*, Wi-Fi internal, radio digital dengan protokol terbuka). Ketika ground station atau frekuensi radio disusupi, penyerang dapat menyuntikkan paket data berbahaya secara instan untuk mengubah arah propulsi (*burn vector*).
* **Kerapuhan Sistem Berbasis Black-box LLM:** Mencoba menghubungkan AI biasa (*vibe coding*) ke sistem pemandu roket sangat berbahaya karena risiko halusinasi angka register, salah format data biner, dan eksekusi perintah destruktif di ruang hampa.

### 2.2 Solusi "Frankenstein" Apollo-26
* **Zero Network Interface:** Mesin kalkulasi AGC sama sekali tidak memiliki tumpukan TCP/IP atau modul nirkabel.
* **Acoustic Transceiver Protocol:** Instruksi telemetri dimodulasi menjadi sinyal audio analog di udara.
* **Spec-Driven Determinism:** Agen Kiro bertindak sebagai *Autonomous Flight Director* yang diikat oleh kontrak spesifikasi formal di `/.kiro/specs/requirements.md` dan aturan keselamatan `/.kiro/steering/agc-safety-rules.md`.

### 2.3 Metrik Dampak Nyata (Potential Impact: 20%)
* **Permukaan Serangan Siber Jaringan:** Turun menjadi **$0\text{ dB}$ (Nir-koneksi IP)**.
* **Keandalan Dekoding Audio:** **$100\%$ validasi checksum CRC-16** pada uji derau bising hingga rasio SNR rendah.
* **Kecepatan Triase Manuver:** Mengurangi waktu verifikasi instruksi darurat dari 20 menit (penghitungan manual oleh insinyur) menjadi **$\le 10$ detik**.

---

## 3. The "Chimera" System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                 MODERN GROUND STATION (2026)                │
│  - Orbital Drift Vector Calculation                         │
│  - Audio FSK Bell-202 Modulator (1200 Hz Mark / 2200 Hz)   │
└──────────────────────────────┬──────────────────────────────┘
                               │
               (((( Gelombang Suara Akustik ))))
                               │
┌──────────────────────────────▼──────────────────────────────┐
│           ACOUSTIC BRIDGE (CUSTOM MCP SERVER)               │
│  - High-res Line-in Audio Spectrogram Streamer              │
│  - FSK Tone Demodulator & CRC-16 Packet Verifier            │
│  - Stdio / SSE JSON-RPC Protocol Endpoint                   │
└──────────────────────────────▲──────────────────────────────┘
                               │
                Model Context Protocol (MCP)
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                      KIRO AGENT CORE                        │
│  - Trigger: /.kiro/hooks/on_acoustic_preamble.json         │
│  - Specs:   /.kiro/specs/requirements.md (EARS)             │
│  - Bounds:  /.kiro/steering/agc-safety-rules.md             │
│  - Verify:  Property-Based Testing (PBT via Hypothesis)     │
└──────────────────────────────┬──────────────────────────────┘
                               │
                    Virtual DSKY Key Sequence
                               │
┌──────────────────────────────▼──────────────────────────────┐
│         APOLLO GUIDANCE COMPUTER BLOCK II (1969)            │
│  - 15-bit Word Memory Architecture (2K Erasable RAM)        │
│  - Colossus 249 / Luminary 99 Mission Software Core         │
│  - DSKY Neon Phosphor Readout (VERB / NOUN / Registers)     │
│  - Automated Program Actuation: P40 (Thrust Vector) / P64   │
└─────────────────────────────────────────────────────────────┘
```

### Elemen Heterogen yang Dijahit:
1. **The Relic (1969):** Inti komputasi biner AGC Block II dengan kata memori 15-bit, 1-bit paritas, serta display DSKY dengan lampu indikator retro (`COMP ACTY`, `UPLINK ACTY`, `KEY REL`).
2. **The Synapse (Akustik Analog):** Modulasi audio Bell-202 yang mengubah data digital menjadi frekuensi biner audio (1200 Hz mewakili bit 1, 2200 Hz mewakili bit 0).
3. **The Pilot (2026):** Orkestrasi agen AI di dalam Kiro IDE yang bertindak berdasarkan spesifikasi formal, bukan prompt probabilistik lepas kendali.

---

## 4. Design System & Aesthetic Specification (Awwwards-Caliber)

Untuk memenangkan kriteria **Design (20%)**, antarmuka web dashboard tidak mengadopsi tampilan dashboard SaaS biasa, melainkan mengusung konsep **Celestial Brutalism & Swiss Aerospace Luxury**:

* **Color Palette:**
  * *Cosmic Void:* `#050608` (latar belakang hitam mutlak dengan partikel ruang).
  * *Lunar Titanium Surface:* `#0a0d12` dan `#0f141c` (panel instrumen bertekstur logam dingin).
  * *Apollo Electrum Gold:* `#e6c875` (aksen emas bangsawan untuk status otorisasi dan kontrol utama).
  * *DSKY Phosphor Neon:* `#00ff88` (pendaran hijau neon segmen CRT dengan efek *glow diffusion*).
* **Typography Hierarchy:**
  * Display Header: *Italiana* (serif anggun bertaraf editorial kemewahan tinggi).
  * UI Elements & Action Labels: *Syne* (sans-serif geometris futuristik berbobot tebal).
  * Telemetry & Monospace Streams: *Space Mono* (monospace standar aerospace).
* **Micro-Interactions & Live Hardware Feedback:**
  * **Interactive FSK Audio Synthesizer:** Pengujian audio real-time menggunakan Web Audio API lokal.
  * **Dynamic Canvas Spectrogram:** Visualisasi waterfall dan sinyal gelombang frekuensi audio secara langsung.
  * **Tactile DSKY Keypad:** Tombol DSKY fisik virtual dengan efek audio klik membran 900 Hz dan lampu peringatan yang menyala sesuai siklus instruksi komputer Apollo.

---

## 5. Functional Requirements (Metodologi EARS)

### 5.1 Acoustic Modulation & Detection
* **FR-1 (Event-Driven):** Saat mikrofon menangkap sinyal audio kontinu 1200 Hz selama $\ge 250\text{ ms}$ (*carrier preamble*), sistem jembatan audio harus memicu *agent hook* Kiro `on_acoustic_preamble.json`.
* **FR-2 (Robustness):** Jika terjadi distorsi volume, gema ruangan, atau gangguan derau bising lingkungan (*ambient noise*), modul demodulator FSK harus memvalidasi checksum CRC-16 dan membuang paket korup tanpa memicu crash pada proses latar belakang.

### 5.2 Kiro Agent & MCP Tooling
* **FR-3 (State-Driven):** Saat Kiro Agent terbangun oleh sinyal audio, agen harus memanggil tool MCP `listen_acoustic_burst(timeout_sec=5)` untuk mengekstrak muatan data menjadi payload JSON terstruktur:
  $$\text{Payload} = \{\text{verb}: \mathbb{Z}, \text{noun}: \mathbb{Z}, \text{program}: \mathbb{Z}, \text{delta\_v}: \mathbb{R}, \text{checksum}: \text{hex}\}$$
* **FR-4 (Ubiquitous):** Sistem Kiro Agent harus selalu memvalidasi setiap rencana penekanan tombol DSKY terhadap aturan di `.kiro/steering/agc-safety-rules.md` sebelum tool eksekusi dipanggil.
* **FR-5 (Unwanted Behavior):** Jika payload meminta instruksi kritis tingkat tinggi (seperti `VERB 97` Engine Cut-off atau perubahan Program P00 saat manuver pembakaran berlangsung), agen dilarang mengeksekusi instruksi tersebut sebelum menerima *Operator Signature Token* dari antarmuka stasiun bumi.

### 5.3 AGC & DSKY Emulation Interface
* **FR-6 (Event-Driven):** Saat payload manuver orbital tervalidasi, agen Kiro harus memanggil tool `execute_dsky_sequence(keys=[...])` untuk menginjeksi urutan tombol ke bus memori AGC dengan interval clock minimal $100\text{ ms}$ antar penekanan tombol.
* **FR-7 (State-Driven):** Selama eksekusi program pemandu (contoh: P40 Thrust Vector), emulator AGC harus memperbarui register R1 (Azimuth), R2 (Elevation), dan R3 (Delta-V) serta menyalakan lampu indikator `COMP ACTY` secara berkala.

---

## 6. Non-Functional Requirements & Performance Targets

| Parameter | Target Spesifikasi | Keterangan Rekayasa |
| :--- | :--- | :--- |
| **Baud Rate Akustik** | 300 s.d. 1200 baud | Standar audio Bell-202 yang stabil untuk speaker dan mikrofon laptop standar. |
| **E2E Latency** | $\le 2.0\text{ detik}$ | Dari nada suara pertama dibunyikan hingga register DSKY diperbarui. |
| **PBT Fuzzing Coverage** | 100% lolos pada $10.000$ kasus uji | Pengujian acak terhadap noise audio menggunakan library `Hypothesis` / `fast-check`. |
| **Isolasi Jaringan** | $0\text{ outbound socket calls}$ | Seluruh simulasi AGC dan server MCP berjalan 100% offline di localhost. |
| **Resource Footprint** | RAM $\le 256\text{ MB}$, CPU $\le 5\%$ | Ringan, deterministik, dan dapat dijalankan di lingkungan pengujian juri Devpost. |

---

## 7. Deep Kiro Feature Integration

### 7.1 Custom MCP Server (`/mcp-server/`)
Server lokal yang berkomunikasi dengan Kiro IDE via JSON-RPC melalui `stdio`:
* `listen_acoustic_burst(timeout_sec)`: Menangkap stream audio lokal dan mengonversinya menjadi frame heksadesimal.
* `inspect_agc_status()`: Membaca isi register memori 15-bit (Accumulator, Z-register, status lampu DSKY).
* `execute_dsky_sequence(keys)`: Mengirimkan deretan penekanan tombol (`VERB`, `NOUN`, angka 0-9, `PROCEED`, `ENTER`).
* `verify_crc16(payload, checksum)`: Memvalidasi integritas matematis paket data biner.

### 7.2 Agent Hooks (`.kiro/hooks/on_acoustic_preamble.json`)
```json
{
  "event": "acoustic_carrier_detected",
  "matcher": {
    "frequency_hz": 1200,
    "duration_ms": 250
  },
  "action": "start_spec_session",
  "spec_path": ".kiro/specs/requirements.md",
  "prompt": "Sinyal transmisi pembawa akustik darurat terdeteksi. Panggil tool listen_acoustic_burst, lakukan dekode FSK, verifikasi CRC-16, dan jalankan urutan manuver DSKY sesuai batasan keamanan agc-safety-rules.md."
}
```

### 7.3 Steering Rules (`.kiro/steering/agc-safety-rules.md`)
* Membatasi ruang lingkup agen:
  1. Hanya boleh berinteraksi melalui perkakas MCP resmi (`whitelist`).
  2. Dilarang menjalankan skrip shell sistem operasi induk.
  3. Wajib memverifikasi indikator `KEY REL` sebelum mengirimkan input tombol berikutnya.
  4. Setiap penyimpangan frekuensi audio $> 50\text{ Hz}$ harus dicatat sebagai anomali telemetri.

### 7.4 Property-Based Testing (PBT) Scope
Menguji ketahanan perangkat lunak secara matematis:
* **Invariance Property:** Mengirimkan ribuan sampel audio acak (derau putih, suara batuk manusia, suara klik keyboard) tidak boleh menghasilkan eksekusi tombol liar pada DSKY.
* **Reversibility Property:** Setiap struktur data telemetri valid yang dimodulasi ke FSK dan didekode ulang harus menghasilkan nilai koordinat yang identik tanpa kehilangan presisi.

---

## 8. Directory Layout (Submission Ready)

```text
apollo-26/
├── .kiro/                               # WAJIB (Jangan di-gitignore!)
│   ├── specs/
│   │   ├── requirements.md              # Spesifikasi formal kebutuhan EARS
│   │   ├── design.md                    # Desain arsitektur FSK & AGC Bus
│   │   └── tasks.md                     # Daftar eksekusi bertahap agen Kiro
│   ├── steering/
│   │   ├── agc-safety-rules.md          # Batasan keamanan instruksi Apollo
│   │   └── coding-standards.md          # Standar kode & arsitektur proyek
│   └── hooks/
│       └── on_acoustic_preamble.json    # Hook pemicu otomatis via nada FSK
├── mcp-server/                          # Custom MCP Server (Node.js/Python)
│   ├── src/
│   │   ├── audio_modem.py               # FSK Demodulator (Bell 202 1200/2200Hz)
│   │   ├── agc_connector.py             # Penghubung memori bus simulator AGC
│   │   └── index.py                     # Implementasi JSON-RPC MCP
│   └── tests/
│       └── test_pbt_acoustic.py         # Pengujian berbasis properti (Hypothesis)
├── agc-core/                            # Simulator Logika 1969
│   ├── agc_engine.py                    # Emulator register 15-bit Block II
│   └── dsky_logic.py                    # Logika display dan program penerbangan
├── web-dashboard/                       # Antarmuka Web Pameran (Awwwards Style)
│   ├── index.html                       # Single-file HTML/CSS/JS (DSKY + Audio Engine)
│   └── assets/                          # SVG icon dan audio telemetry sample
├── LICENSE                              # MIT License (Terdeteksi di GitHub About)
├── PRD.md                               # Dokumen spesifikasi produk ini
└── README.md                            # Panduan instalasi, demo YouTube, dan arsitektur
```

---

## 9. Penyelarasan Kriteria Penjurian Devpost ($100,000 Prize Pool)

* **Potential Impact (20%):** Memecahkan kerentanan serangan siber satelit modern dengan mengisolasi jalur data secara akustik (*air-gapped*) pada sistem kendali darurat.
* **Technological Implementation (20%):** Memanfaatkan seluruh ekosistem Kiro secara mendalam (Spec-Driven Development, Custom MCP Server, Agent Hooks, Steering Rules, dan PBT).
* **Design (20%):** Antarmuka web *Celestial Brutalism* dengan mesin sintesis Web Audio API nyata, visualizer spektrogram frekuensi, dan display DSKY neon hijau autentik.
* **Innovation / Idea (20%):** Menjahit komputer pendarat bulan 1969 dengan Agentic AI 2026 melalui media suara analog (bukan kabel atau internet).
* **Presentation (20%):** Video 180 detik terstruktur: nada lengkingan modem audio -> Kiro Hook aktif otomatis -> DSKY memasukkan koordinat pembakaran roket -> orbit satelit terselamatkan.

---

## 10. Rencana Pelaksanaan & Milestone

1. **Milestone 1 (Fondasi Repositori):** Inisialisasi repo GitHub publik dengan lisensi MIT dan berkas `PRD.md`.
2. **Milestone 2 (Spesifikasi Formal Kiro):** Pembuatan dokumen `requirements.md`, `design.md`, dan `tasks.md` di `.kiro/specs/`.
3. **Milestone 3 (Acoustic MCP Server):** Pembuatan modem audio FSK dan pengujian ketahanan PBT.
4. **Milestone 4 (Integrasi AGC & DSKY):** Penyambungan emulator 15-bit AGC ke tool MCP dan konfigurasi Agent Hooks.
5. **Milestone 5 (UI Dashboard & Video Pitch):** Penyelesaian dashboard visual dan perekaman video demo YouTube 3 menit.
6. **Milestone 6 (Submisi & Bonus Prizes):** Publikasi artikel blog (Bonus Blog Prize) dan pos media sosial `#KiroweenHackathon26` (Bonus Social Blitz).