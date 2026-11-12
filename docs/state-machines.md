# Apollo-26 State Machines

State machine ini normatif untuk urutan kontrol. Detail wire format tetap mengikuti `contracts/acoustic-frame-v1.md`.

## 1. Acoustic receiver

```mermaid
stateDiagram-v2
  [*] --> IDLE
  IDLE --> PREAMBLE: mark 1200 Hz terdeteksi
  PREAMBLE --> IDLE: hilang sebelum 250 ms
  PREAMBLE --> SYNC: stabil ≥250 ms
  SYNC --> RECEIVE: A5 26
  SYNC --> IDLE: timeout / mismatch
  RECEIVE --> VALIDATE: 34 byte lengkap
  RECEIVE --> REJECTED: timeout / framing error
  VALIDATE --> ACCEPTED: seluruh gerbang lolos
  VALIDATE --> REJECTED: gerbang gagal
  ACCEPTED --> IDLE: persist seq + publish
  REJECTED --> IDLE: audit reason
```

| State | Input | Guard | Side effect | Error |
| :-- | :-- | :-- | :-- | :-- |
| IDLE | blok audio | energi mark di atas threshold | nyalakan `UPLINK ACTY`, mulai timer | — |
| PREAMBLE | blok audio | mark stabil ≥250 ms | cari sync | drift >50 Hz dicatat |
| SYNC | bits | `A5 26` ditemukan | mulai buffer 34 byte | `SYNC`/timeout |
| RECEIVE | bits 8N1 | 34 byte lengkap | freeze candidate | `LENGTH`/framing |
| VALIDATE | candidate | urutan §4.3 PRD | persist seq atomik | reason pertama |
| ACCEPTED | — | persist sukses | atomic-write inbox + event WS | `INTERNAL` fail-closed |
| REJECTED | — | — | atomic-write rejected audit | daemon tetap hidup |

## 2. DSKY input

```mermaid
stateDiagram-v2
  [*] --> IDLE
  IDLE --> VERB_ENTRY: VERB
  IDLE --> NOUN_ENTRY: NOUN
  VERB_ENTRY --> IDLE: 2 digit + ENTR
  NOUN_ENTRY --> DATA_ENTRY: 2 digit + ENTR (bila noun perlu data)
  NOUN_ENTRY --> EXECUTING: 2 digit + ENTR
  DATA_ENTRY --> EXECUTING: field lengkap + ENTR/PRO
  EXECUTING --> IDLE: selesai
  IDLE --> OPR_ERR: urutan tidak valid
  VERB_ENTRY --> OPR_ERR: urutan tidak valid
  NOUN_ENTRY --> OPR_ERR: urutan tidak valid
  DATA_ENTRY --> OPR_ERR: urutan tidak valid
  OPR_ERR --> IDLE: RSET
```

Invariants:
- Tidak ada tombol diterima ketika `KEY REL` menyala.
- Jarak antar tombol minimal 100 ms.
- `OPR ERR` tidak mengubah program/register dan hanya pulih lewat `RSET`.
- V37 memakai urutan `VERB 3 7 ENTR <program> <program> ENTR`; bukan V37 + NOUN.
- State DSKY dimiliki `agc-core`, bukan DOM frontend.

## 3. Kiro Flight Watch

```mermaid
stateDiagram-v2
  [*] --> STANDBY
  STANDBY --> WAITING: operator mulai Flight Watch
  WAITING --> INSPECTING: await_telemetry_frame → COMMAND
  WAITING --> WAITING: timeout (operator lanjut)
  INSPECTING --> PLANNING: inspect_agc_status sukses
  INSPECTING --> HALTED: AGC unavailable / KEY REL
  PLANNING --> AUTH_WAIT: safety gate: AUTH_REQUIRED
  PLANNING --> EXECUTING: rencana kanonik + gate ALLOW
  AUTH_WAIT --> EXECUTING: AUTH valid untuk frame_seq
  AUTH_WAIT --> HALTED: timeout / AUTH invalid
  EXECUTING --> VERIFYING: execute_dsky_sequence selesai
  VERIFYING --> WAITING: state AGC sesuai postcondition
  VERIFYING --> HALTED: mismatch / OPR ERR
  HALTED --> WAITING: operator acknowledge + safe state
  WAITING --> STANDBY: operator stop
```

| Transisi | Tool wajib | Fail-closed condition |
| :-- | :-- | :-- |
| WAITING → INSPECTING | `await_telemetry_frame` | frame tidak valid tidak pernah keluar dari daemon |
| INSPECTING → PLANNING | `inspect_agc_status` | status gagal/KEY REL → tidak execute |
| PLANNING → gate | `plan_dsky_sequence` | rencana agen ≠ kanonik → tidak execute |
| gate → EXECUTING | `execute_dsky_sequence(keys, frame_seq)` | safety gate selalu hitung ulang aturan |
| EXECUTING → VERIFYING | `inspect_agc_status` | OPR ERR/mismatch → HALTED |

## 4. COMMAND/AUTH lifecycle

```mermaid
stateDiagram-v2
  [*] --> VALIDATED
  VALIDATED --> READY: non-critical
  VALIDATED --> HELD: critical tanpa AUTH
  HELD --> READY: AUTH.ref_seq cocok
  HELD --> EXPIRED: 120 s
  READY --> EXECUTED: DSKY postcondition benar
  READY --> FAILED: execution error
  EXECUTED --> [*]
  EXPIRED --> [*]
  FAILED --> [*]
```

AUTH bersifat satu kali. `EXECUTED`, `EXPIRED`, atau `FAILED` menutup command; AUTH berikutnya untuk `ref_seq` yang sama ditolak dengan `STATE`.