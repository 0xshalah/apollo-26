# Apollo-26 Acoustic Frame Protocol v1

**Status:** Normative draft · **Wire size:** 34 bytes · **Byte order:** big-endian unless stated otherwise.

Kata **MUST**, **MUST NOT**, **SHOULD**, dan **MAY** bersifat normatif. Bila dokumen lain berbeda, kontrak ini menjadi sumber kebenaran wire format; perubahan wajib menaikkan versi atau memperbarui seluruh golden vector.

## 1. Physical encoding
- Mark = 1200 Hz (bit 1), space = 2200 Hz (bit 0).
- 300 symbols/s; continuous phase.
- Preamble = mark kontinu minimal 250 ms.
- Setiap byte memakai 8N1: satu start bit `0`, delapan data bit LSB-first, satu stop bit `1`.
- Setelah preamble, transmitter mengirim seluruh 34 byte tanpa jeda antar-frame.

## 2. Wire layout
| Offset | Panjang | Field | Encoding |
| --: | --: | :-- | :-- |
| 0 | 2 | `sync` | Konstan `A5 26` |
| 2 | 1 | `version` | Konstan `01` |
| 3 | 1 | `frame_type` | `01 COMMAND`, `02 AUTH` |
| 4 | 4 | `seq` | uint32 BE, 1..4294967295 |
| 8 | 4 | `ref_seq` | uint32 BE |
| 12 | 1 | `flags` | bit0 `CRITICAL`; bit1–7 MUST 0 |
| 13 | 1 | `verb` | uint8, 0..99 |
| 14 | 1 | `noun` | uint8, 0..99 |
| 15 | 1 | `program` | uint8, 0..99 |
| 16 | 2 | `r1` | int16 two's-complement BE, centidegree |
| 18 | 2 | `r2` | int16 two's-complement BE, centidegree |
| 20 | 4 | `delta_v` | int32 two's-complement BE, 0.1 ft/s |
| 24 | 8 | `hmac` | 8 byte pertama HMAC-SHA256 atas byte 2..23 |
| 32 | 2 | `crc` | CRC-16/CCITT-FALSE atas byte 2..31 |

CRC-16/CCITT-FALSE: polynomial `0x1021`, init `0xFFFF`, refin `false`, refout `false`, xorout `0x0000`.

HMAC truncation 64-bit dipilih untuk demo dengan frame pendek; ini bukan rekomendasi sistem penerbangan produksi.

## 3. Semantic constraints
### COMMAND (`frame_type=01`)
- `ref_seq` MUST 0.
- HMAC key = UTF-8 bytes dari `APOLLO26_LINK_KEY`.
- `verb`, `noun`, `program`, `r1`, `r2`, dan `delta_v` membawa payload perintah.
- `CRITICAL` MUST diset bila safety policy mengklasifikasikan perintah sebagai kritis. Receiver tidak boleh mempercayai flag ini sebagai satu-satunya klasifikasi; safety gate menghitung ulang.

### AUTH (`frame_type=02`)
- `ref_seq` MUST menunjuk COMMAND yang masih tertahan dan belum pernah diotorisasi.
- HMAC key = UTF-8 bytes dari `APOLLO26_OPERATOR_KEY`.
- `flags`, `verb`, `noun`, `program`, `r1`, `r2`, dan `delta_v` MUST 0.
- AUTH berlaku satu kali untuk satu `ref_seq`; setelah eksekusi atau kedaluwarsa, AUTH tidak dapat dipakai ulang.
- AUTH yang tiba sebelum COMMAND MAY disimpan maksimal 30 detik; implementasi awal SHOULD menolak untuk menyederhanakan state.

## 4. Sequence and restart behavior
- `seq` global lintas COMMAND dan AUTH dan MUST lebih besar dari `last_accepted_seq`.
- Daemon MUST menyimpan `last_accepted_seq` secara atomik sebelum menerbitkan frame ke konsumen.
- Nilai `0` tidak valid.
- Wraparound tidak didukung v1. Bila `last_accepted_seq=0xFFFFFFFF`, link masuk fail-closed sampai operator melakukan reprovisioning eksplisit.
- Reset sequence counter bukan operasi UI biasa dan MUST menghapus pending command/AUTH.

## 5. Validation order
Receiver MUST melakukan urutan berikut dan berhenti pada kegagalan pertama:
1. Panjang tepat 34 byte.
2. Sync `A5 26`.
3. Version dan frame type dikenal.
4. CRC valid.
5. Reserved flags nol dan semantic constraints sesuai tipe.
6. HMAC valid dengan perbandingan constant-time dan key yang sesuai frame type.
7. `seq > last_accepted_seq`.
8. Range field dan aturan domain valid.
9. Persist `seq` atomik, lalu terbitkan frame.

Kode alasan stabil: `LENGTH`, `SYNC`, `VERSION`, `TYPE`, `CRC`, `FLAGS`, `HMAC`, `REPLAY`, `RANGE`, `STATE`, `INTERNAL`.

## 6. Canonical demo keys
Hanya untuk golden vector dan demo publik; **bukan rahasia**:
- Link: `apollo26-link-demo-key-v1`
- Operator: `apollo26-operator-demo-key-v1`

Deployment lokal membaca key dari environment. `.env` tidak boleh di-commit.

## 7. Golden vectors
Lihat `contracts/vectors/frames.json`. Dua vektor awal dihitung secara independen dengan primitive .NET dan harus diverifikasi ulang oleh implementasi Python serta TypeScript sebelum ditandai `verified`.

## 8. Open design decision
Ambang `abs(delta_v)` yang membuat COMMAND kritis ditentukan di spec `mcp-bridge`, bukan wire protocol. Sampai ditetapkan, safety gate MUST memperlakukan aktivasi P40 sebagai kritis.