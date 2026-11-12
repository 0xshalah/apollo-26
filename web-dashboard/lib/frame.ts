/**
 * Apollo-26 acoustic frame v1 codec (contracts/acoustic-frame-v1.md).
 *
 * Pure module: no DOM, storage, clock, or network access. HMAC is computed by an
 * injected `HmacSigner`, so the codec can run in Node tests and in the browser.
 */

export const FRAME_SIZE = 34;
export const SYNC = [0xa5, 0x26] as const;
export const VERSION = 0x01;
export const MAX_SEQ = 0xffffffff;
export const HMAC_OFFSET = 24;
export const HMAC_LENGTH = 8;
export const CRC_OFFSET = 32;

export const FRAME_TYPE_CODE = { COMMAND: 0x01, AUTH: 0x02 } as const;
export type FrameType = keyof typeof FRAME_TYPE_CODE;

export const FLAG_CRITICAL = 0x01;

/** Stable reason codes from contract §5 (plus OK for accepted frames). */
export const REASON_CODES = [
  'LENGTH',
  'SYNC',
  'VERSION',
  'TYPE',
  'CRC',
  'FLAGS',
  'HMAC',
  'REPLAY',
  'RANGE',
  'STATE',
  'INTERNAL',
] as const;
export type RejectReason = (typeof REASON_CODES)[number];

/** Wire field layout: [offset, length]. */
export const FIELD_LAYOUT = [
  { name: 'sync', offset: 0, length: 2 },
  { name: 'version', offset: 2, length: 1 },
  { name: 'frame_type', offset: 3, length: 1 },
  { name: 'seq', offset: 4, length: 4 },
  { name: 'ref_seq', offset: 8, length: 4 },
  { name: 'flags', offset: 12, length: 1 },
  { name: 'verb', offset: 13, length: 1 },
  { name: 'noun', offset: 14, length: 1 },
  { name: 'program', offset: 15, length: 1 },
  { name: 'r1', offset: 16, length: 2 },
  { name: 'r2', offset: 18, length: 2 },
  { name: 'delta_v', offset: 20, length: 4 },
  { name: 'hmac', offset: 24, length: 8 },
  { name: 'crc', offset: 32, length: 2 },
] as const;
export type FieldName = (typeof FIELD_LAYOUT)[number]['name'];

/** Domain value of a frame; field names mirror contracts/vectors/frames.json. */
export interface FrameFields {
  frame_type: FrameType;
  seq: number;
  ref_seq: number;
  critical: boolean;
  verb: number;
  noun: number;
  program: number;
  r1_centidegrees: number;
  r2_centidegrees: number;
  delta_v_tenths_fps: number;
}

export interface HmacSigner {
  signSha256(key: Uint8Array, message: Uint8Array): Promise<Uint8Array>;
}

export class FrameValueError extends Error {
  constructor(
    readonly field: keyof FrameFields,
    message: string,
  ) {
    super(message);
    this.name = 'FrameValueError';
  }
}

const isIntIn = (v: number, min: number, max: number): boolean =>
  Number.isInteger(v) && v >= min && v <= max;

/** Checks wire ranges and COMMAND/AUTH semantics before encoding. */
export function assertEncodable(f: FrameFields): void {
  const check = (field: keyof FrameFields, ok: boolean, msg: string) => {
    if (!ok) throw new FrameValueError(field, msg);
  };
  check('frame_type', f.frame_type === 'COMMAND' || f.frame_type === 'AUTH', 'unknown frame type');
  check('seq', isIntIn(f.seq, 1, MAX_SEQ), 'seq must be an integer 1..4294967295');
  check('ref_seq', isIntIn(f.ref_seq, 0, MAX_SEQ), 'ref_seq must be an integer 0..4294967295');
  check('verb', isIntIn(f.verb, 0, 99), 'verb must be 0..99');
  check('noun', isIntIn(f.noun, 0, 99), 'noun must be 0..99');
  check('program', isIntIn(f.program, 0, 99), 'program must be 0..99');
  check('r1_centidegrees', isIntIn(f.r1_centidegrees, -32768, 32767), 'r1 must be int16');
  check('r2_centidegrees', isIntIn(f.r2_centidegrees, -32768, 32767), 'r2 must be int16');
  check(
    'delta_v_tenths_fps',
    isIntIn(f.delta_v_tenths_fps, -2147483648, 2147483647),
    'delta_v must be int32',
  );
  if (f.frame_type === 'COMMAND') {
    check('ref_seq', f.ref_seq === 0, 'COMMAND ref_seq must be 0');
  } else {
    check('ref_seq', f.ref_seq !== 0, 'AUTH ref_seq must reference a COMMAND (nonzero)');
    check('critical', !f.critical, 'AUTH flags must be 0');
    check('verb', f.verb === 0, 'AUTH verb must be 0');
    check('noun', f.noun === 0, 'AUTH noun must be 0');
    check('program', f.program === 0, 'AUTH program must be 0');
    check('r1_centidegrees', f.r1_centidegrees === 0, 'AUTH r1 must be 0');
    check('r2_centidegrees', f.r2_centidegrees === 0, 'AUTH r2 must be 0');
    check('delta_v_tenths_fps', f.delta_v_tenths_fps === 0, 'AUTH delta_v must be 0');
  }
}

/** CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflection, xorout 0. */
export function crc16CcittFalse(data: Uint8Array): number {
  let crc = 0xffff;
  for (const byte of data) {
    crc ^= byte << 8;
    for (let i = 0; i < 8; i++) {
      crc = crc & 0x8000 ? ((crc << 1) ^ 0x1021) & 0xffff : (crc << 1) & 0xffff;
    }
  }
  return crc;
}

/** Writes bytes 0..23 (everything before HMAC). */
export function encodeBody(f: FrameFields): Uint8Array {
  assertEncodable(f);
  const out = new Uint8Array(FRAME_SIZE);
  const view = new DataView(out.buffer);
  out[0] = SYNC[0];
  out[1] = SYNC[1];
  out[2] = VERSION;
  out[3] = FRAME_TYPE_CODE[f.frame_type];
  view.setUint32(4, f.seq, false);
  view.setUint32(8, f.ref_seq, false);
  out[12] = f.critical ? FLAG_CRITICAL : 0;
  out[13] = f.verb;
  out[14] = f.noun;
  out[15] = f.program;
  view.setInt16(16, f.r1_centidegrees, false);
  view.setInt16(18, f.r2_centidegrees, false);
  view.setInt32(20, f.delta_v_tenths_fps, false);
  return out;
}

export async function computeTag(
  signer: HmacSigner,
  key: Uint8Array,
  frame: Uint8Array,
): Promise<Uint8Array> {
  const mac = await signer.signSha256(key, frame.slice(2, HMAC_OFFSET));
  if (mac.length < HMAC_LENGTH) throw new Error('HMAC output too short');
  return mac.slice(0, HMAC_LENGTH);
}

/** Writes CRC over bytes 2..31 into bytes 32..33 (mutates `frame`). */
export function writeCrc(frame: Uint8Array): void {
  const crc = crc16CcittFalse(frame.subarray(2, CRC_OFFSET));
  frame[CRC_OFFSET] = crc >> 8;
  frame[CRC_OFFSET + 1] = crc & 0xff;
}

/**
 * Encodes and signs a frame. `key` is the UTF-8 link key for COMMAND or the
 * operator key for AUTH. Returns a fresh 34-byte array.
 */
export async function encodeFrame(
  f: FrameFields,
  key: Uint8Array,
  signer: HmacSigner,
): Promise<Uint8Array> {
  const frame = encodeBody(f);
  const tag = await computeTag(signer, key, frame);
  frame.set(tag, HMAC_OFFSET);
  writeCrc(frame);
  return frame;
}

function semanticsValid(bytes: Uint8Array, f: FrameFields, flags: number): boolean {
  if (flags & 0xfe) return false;
  if (f.frame_type === 'COMMAND') return f.ref_seq === 0;
  return (
    f.ref_seq !== 0 &&
    flags === 0 &&
    bytes.subarray(13, 24).every((b) => b === 0)
  );
}

function rangesValid(f: FrameFields): boolean {
  return f.seq !== 0 && [f.verb, f.noun, f.program].every((v) => v >= 0 && v <= 99);
}

/** Parses fields at normative offsets without validating CRC/HMAC. */
export function parseFields(bytes: Uint8Array): FrameFields & { flags: number } {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const type = bytes[3] === FRAME_TYPE_CODE.COMMAND ? 'COMMAND' : 'AUTH';
  const flags = bytes[12];
  return {
    frame_type: type,
    seq: view.getUint32(4, false),
    ref_seq: view.getUint32(8, false),
    flags,
    critical: (flags & FLAG_CRITICAL) !== 0,
    verb: bytes[13],
    noun: bytes[14],
    program: bytes[15],
    r1_centidegrees: view.getInt16(16, false),
    r2_centidegrees: view.getInt16(18, false),
    delta_v_tenths_fps: view.getInt32(20, false),
  };
}

export type DecodeResult =
  | { ok: true; frame: FrameFields }
  | { ok: false; reason: RejectReason };

export interface FrameKeys {
  link: Uint8Array;
  operator: Uint8Array;
}

function constantTimeEqual(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}

function toDomain(p: FrameFields & { flags: number }): FrameFields {
  return {
    frame_type: p.frame_type,
    seq: p.seq,
    ref_seq: p.ref_seq,
    critical: p.critical,
    verb: p.verb,
    noun: p.noun,
    program: p.program,
    r1_centidegrees: p.r1_centidegrees,
    r2_centidegrees: p.r2_centidegrees,
    delta_v_tenths_fps: p.delta_v_tenths_fps,
  };
}

/**
 * Validation oracle following contract §5 order. `lastAcceptedSeq` null skips
 * the replay gate (pure decode); a number applies `seq > lastAcceptedSeq`.
 * The daemon remains the authority; this mirrors it for tests and preview.
 */
export async function validateFrame(
  bytes: Uint8Array,
  keys: FrameKeys,
  signer: HmacSigner,
  lastAcceptedSeq: number | null = null,
): Promise<DecodeResult> {
  if (bytes.length !== FRAME_SIZE) return { ok: false, reason: 'LENGTH' };
  if (bytes[0] !== SYNC[0] || bytes[1] !== SYNC[1]) return { ok: false, reason: 'SYNC' };
  if (bytes[2] !== VERSION) return { ok: false, reason: 'VERSION' };
  if (bytes[3] !== FRAME_TYPE_CODE.COMMAND && bytes[3] !== FRAME_TYPE_CODE.AUTH) {
    return { ok: false, reason: 'TYPE' };
  }
  const crc = (bytes[CRC_OFFSET] << 8) | bytes[CRC_OFFSET + 1];
  if (crc16CcittFalse(bytes.subarray(2, CRC_OFFSET)) !== crc) return { ok: false, reason: 'CRC' };
  const parsed = parseFields(bytes);
  if (!semanticsValid(bytes, parsed, parsed.flags)) return { ok: false, reason: 'FLAGS' };
  const key = parsed.frame_type === 'COMMAND' ? keys.link : keys.operator;
  const expected = await computeTag(signer, key, bytes);
  if (!constantTimeEqual(bytes.subarray(HMAC_OFFSET, CRC_OFFSET), expected)) {
    return { ok: false, reason: 'HMAC' };
  }
  if (lastAcceptedSeq !== null && !(parsed.seq !== 0 && parsed.seq > lastAcceptedSeq)) {
    return { ok: false, reason: 'REPLAY' };
  }
  if (!rangesValid(parsed)) return { ok: false, reason: 'RANGE' };
  return { ok: true, frame: toDomain(parsed) };
}

/** Authenticated decode (no replay gate). */
export function decodeFrame(
  bytes: Uint8Array,
  keys: FrameKeys,
  signer: HmacSigner,
): Promise<DecodeResult> {
  return validateFrame(bytes, keys, signer, null);
}

export function toHex(bytes: Uint8Array): string {
  let s = '';
  for (const b of bytes) s += b.toString(16).padStart(2, '0');
  return s;
}

export function fromHex(hex: string): Uint8Array {
  if (!/^(?:[0-9a-fA-F]{2})*$/.test(hex)) throw new Error('invalid hex');
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return out;
}

export const utf8 = (s: string): Uint8Array => new TextEncoder().encode(s);

/** Web Crypto adapter. `subtle` is passed explicitly by the caller. */
export function webCryptoSigner(subtle: SubtleCrypto): HmacSigner {
  return {
    async signSha256(key, message) {
      const cryptoKey = await subtle.importKey(
        'raw',
        new Uint8Array(key),
        { name: 'HMAC', hash: 'SHA-256' },
        false,
        ['sign'],
      );
      const sig = await subtle.sign('HMAC', cryptoKey, new Uint8Array(message));
      return new Uint8Array(sig);
    },
  };
}

/** Canonical AUTH fields: everything except seq/ref_seq is zero by construction. */
export function authFields(seq: number, refSeq: number): FrameFields {
  return {
    frame_type: 'AUTH',
    seq,
    ref_seq: refSeq,
    critical: false,
    verb: 0,
    noun: 0,
    program: 0,
    r1_centidegrees: 0,
    r2_centidegrees: 0,
    delta_v_tenths_fps: 0,
  };
}
