# Apollo-26 Acoustic Frame Protocol v1

**Status:** Normative draft · **Wire size:** 34 bytes · **Byte order:** big-endian unless stated otherwise.

The words **MUST**, **MUST NOT**, **SHOULD**, and **MAY** are normative. If another document differs, this contract is the source of truth for the wire format; a change must bump the version or update every golden vector.

## 1. Physical encoding
- Mark = 1200 Hz (bit 1), space = 2200 Hz (bit 0).
- 300 symbols/s; continuous phase.
- Preamble = continuous mark of at least 250 ms.
- Every byte uses 8N1: one start bit `0`, eight data bits LSB-first, one stop bit `1`.
- After the preamble, the transmitter sends all 34 bytes with no gap.

## 2. Wire layout
| Offset | Length | Field | Encoding |
| --: | --: | :-- | :-- |
| 0 | 2 | `sync` | Constant `A5 26` |
| 2 | 1 | `version` | Constant `01` |
| 3 | 1 | `frame_type` | `01 COMMAND`, `02 AUTH` |
| 4 | 4 | `seq` | uint32 BE, 1..4294967295 |
| 8 | 4 | `ref_seq` | uint32 BE |
| 12 | 1 | `flags` | bit0 `CRITICAL`; bits 1–7 MUST be 0 |
| 13 | 1 | `verb` | uint8, 0..99 |
| 14 | 1 | `noun` | uint8, 0..99 |
| 15 | 1 | `program` | uint8, 0..99 |
| 16 | 2 | `r1` | int16 two's-complement BE, centidegrees |
| 18 | 2 | `r2` | int16 two's-complement BE, centidegrees |
| 20 | 4 | `delta_v` | int32 two's-complement BE, 0.1 ft/s |
| 24 | 8 | `hmac` | First 8 bytes of HMAC-SHA256 over bytes 2..23 |
| 32 | 2 | `crc` | CRC-16/CCITT-FALSE over bytes 2..31 |

CRC-16/CCITT-FALSE: polynomial `0x1021`, init `0xFFFF`, refin `false`, refout `false`, xorout `0x0000`.

The 64-bit HMAC truncation was chosen for a short demo frame; it is not a recommendation for production flight systems.

## 3. Semantic constraints
### COMMAND (`frame_type=01`)
- `ref_seq` MUST be 0.
- HMAC key = UTF-8 bytes of `APOLLO26_LINK_KEY`.
- `verb`, `noun`, `program`, `r1`, `r2`, and `delta_v` carry the command payload.
- `CRITICAL` MUST be set when the safety policy classifies the command as critical. The receiver must not trust this flag as the only classification; the safety gate recomputes it.

### AUTH (`frame_type=02`)
- `ref_seq` MUST point to a COMMAND that is still held and has never been authorized.
- HMAC key = UTF-8 bytes of `APOLLO26_OPERATOR_KEY`.
- `flags`, `verb`, `noun`, `program`, `r1`, `r2`, and `delta_v` MUST be 0.
- An AUTH is valid once for one `ref_seq`; after execution or expiry it cannot be reused.
- An AUTH that arrives before its COMMAND MAY be stored for at most 30 seconds; the initial implementation SHOULD reject it to keep state simple.

## 4. Sequence and restart behavior
- `seq` is global across COMMAND and AUTH and MUST be greater than `last_accepted_seq`.
- The daemon MUST store `last_accepted_seq` atomically before publishing a frame to consumers.
- The value `0` is invalid.
- v1 does not support wraparound. When `last_accepted_seq=0xFFFFFFFF`, the link fails closed until the operator explicitly reprovisions it.
- Resetting the sequence counter is not a normal UI operation and MUST clear pending commands/AUTH.

## 5. Validation order
The receiver MUST perform the following steps in order and stop at the first failure:
1. Length is exactly 34 bytes.
2. Sync `A5 26`.
3. Version and frame type are known.
4. CRC is valid.
5. Reserved flags are zero and semantic constraints match the type.
6. HMAC is valid, using a constant-time comparison and the key for the frame type.
7. `seq > last_accepted_seq`.
8. Field ranges and domain rules are valid.
9. Persist `seq` atomically, then publish the frame.

Stable reason codes: `LENGTH`, `SYNC`, `VERSION`, `TYPE`, `CRC`, `FLAGS`, `HMAC`, `REPLAY`, `RANGE`, `STATE`, `INTERNAL`.

### 5.1 Receiver-side recovery (non-normative for the wire)
The v1 wire format does not change. A receiver MAY run a soft-decision fallback after a valid preamble when the strict decoder fails (`acoustic/soft_decoder.py`, `acoustic/recovery.py`):
- CRC-16 MAY be used to **select** one candidate from soft-bit hypotheses (combining up to 3 copies and flipping at most the 8 weakest CRC-covered bits). Sync bytes MUST NOT be flipped.
- The selected candidate MUST still pass the whole validation order in §5 from step 1, including HMAC and replay.
- A transmitter MAY send identical repeated bursts (preamble + 34 bytes per copy). A receiver MAY report byte-identical copies within 6 s as duplicates of one transmission, not as new frames.

## 6. Canonical demo keys
Only for golden vectors and the public demo; **not secret**:
- Link: `apollo26-link-demo-key-v1`
- Operator: `apollo26-operator-demo-key-v1`

Local deployments read keys from the environment. `.env` must not be committed.

## 7. Golden vectors
See `contracts/vectors/frames.json`. The first two vectors were computed independently with .NET primitives and must be re-verified by the Python and TypeScript implementations before being marked `verified`.

## 8. Open design decision
The `abs(delta_v)` threshold that makes a COMMAND critical is set in the `mcp-bridge` spec, not the wire protocol. Until it is set, the safety gate MUST treat P40 activation as critical.
