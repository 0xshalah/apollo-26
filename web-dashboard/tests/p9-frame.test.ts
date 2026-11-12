import { readFileSync } from 'node:fs';
import path from 'node:path';
import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import {
  authFields,
  crc16CcittFalse,
  decodeFrame,
  encodeFrame,
  FIELD_LAYOUT,
  FRAME_SIZE,
  fromHex,
  REASON_CODES,
  toHex,
  utf8,
  validateFrame,
  webCryptoSigner,
  type FrameFields,
} from '../lib/frame';

const REPO = path.resolve(import.meta.dirname, '..', '..');
const vectorsDoc = JSON.parse(readFileSync(path.join(REPO, 'contracts/vectors/frames.json'), 'utf8')) as {
  demo_keys: { link: string; operator: string };
  vectors: Array<{
    id: string;
    frame?: FrameFields;
    key?: 'link' | 'operator';
    expected_hex?: string;
    expected_verdict: 'ACCEPTED' | 'REJECTED';
    expected_reason?: string;
    derived_from?: string;
    mutation?: { byte_offset: number; xor: number; recompute_crc: boolean };
    precondition?: { last_accepted_seq: number };
  }>;
};
const contractDoc = readFileSync(path.join(REPO, 'contracts/acoustic-frame-v1.md'), 'utf8');

const signer = webCryptoSigner(globalThis.crypto.subtle);
const keys = { link: utf8(vectorsDoc.demo_keys.link), operator: utf8(vectorsDoc.demo_keys.operator) };
const keyFor = (k: 'link' | 'operator') => keys[k];

const FULL = process.env.APOLLO26_PBT_PROFILE === 'full';
const NUM_RUNS = FULL ? 10_000 : 300;

describe('P9 golden vectors (contracts/vectors/frames.json)', () => {
  const canonical = vectorsDoc.vectors.filter((v) => v.expected_hex && v.frame && v.key);

  it('test_p9_vectors_present', () => {
    expect(canonical.length).toBeGreaterThanOrEqual(2);
  });

  for (const v of canonical) {
    it(`test_p9_golden_${v.id}_matches_expected_hex`, async () => {
      const bytes = await encodeFrame(v.frame!, keyFor(v.key!), signer);
      expect(bytes.length).toBe(FRAME_SIZE);
      expect(toHex(bytes)).toBe(v.expected_hex);
      const decoded = await decodeFrame(bytes, keys, signer);
      expect(decoded).toEqual({ ok: true, frame: v.frame });
    });
  }

  for (const v of vectorsDoc.vectors.filter((x) => x.derived_from)) {
    it(`test_p9_derived_${v.id}_yields_${v.expected_reason}`, async () => {
      const base = vectorsDoc.vectors.find((x) => x.id === v.derived_from)!;
      const bytes = fromHex(base.expected_hex!);
      if (v.mutation) {
        bytes[v.mutation.byte_offset] ^= v.mutation.xor;
        if (v.mutation.recompute_crc) throw new Error('recompute_crc mutation not supported by this test');
      }
      const last = v.precondition?.last_accepted_seq ?? 0;
      const result = await validateFrame(bytes, keys, signer, last);
      expect(v.expected_verdict).toBe('REJECTED');
      expect(result).toEqual({ ok: false, reason: v.expected_reason });
    });
  }
});

describe('protocol constants equal the normative contract', () => {
  it('test_p9_layout_matches_contract_table', () => {
    for (const f of FIELD_LAYOUT) {
      const re = new RegExp(`\\|\\s*${f.offset}\\s*\\|\\s*${f.length}\\s*\\|\\s*\`${f.name}\``);
      expect(contractDoc, `layout row for ${f.name}`).toMatch(re);
    }
    const last = FIELD_LAYOUT[FIELD_LAYOUT.length - 1];
    expect(last.offset + last.length).toBe(FRAME_SIZE);
    expect(contractDoc).toMatch(new RegExp(`Wire size:\\*\\*\\s*${FRAME_SIZE} bytes`));
  });

  it('test_p9_reason_codes_match_contract', () => {
    const line = contractDoc.split('\n').find((l) => l.startsWith('Kode alasan stabil'))!;
    const codes = [...line.matchAll(/`([A-Z]+)`/g)].map((m) => m[1]);
    expect(codes).toEqual([...REASON_CODES]);
  });

  it('test_p9_crc_check_value', () => {
    // CRC-16/CCITT-FALSE catalogue check value for ASCII "123456789".
    expect(crc16CcittFalse(utf8('123456789'))).toBe(0x29b1);
  });
});

const uint32NonZero = fc.integer({ min: 1, max: 0xffffffff });
const uint32Boundary = fc.oneof(fc.constantFrom(1, 2, 0x7fffffff, 0x80000000, 0xfffffffe, 0xffffffff), uint32NonZero);
const int16 = fc.oneof(fc.constantFrom(-32768, -1, 0, 1, 32767), fc.integer({ min: -32768, max: 32767 }));
const int32 = fc.oneof(
  fc.constantFrom(-2147483648, -1, 0, 1, 2147483647),
  fc.integer({ min: -2147483648, max: 2147483647 }),
);
const uint8Dec = fc.integer({ min: 0, max: 99 });

const commandArb: fc.Arbitrary<FrameFields> = fc.record({
  frame_type: fc.constant('COMMAND' as const),
  seq: uint32Boundary,
  ref_seq: fc.constant(0),
  critical: fc.boolean(),
  verb: uint8Dec,
  noun: uint8Dec,
  program: uint8Dec,
  r1_centidegrees: int16,
  r2_centidegrees: int16,
  delta_v_tenths_fps: int32,
});
const authArb: fc.Arbitrary<FrameFields> = fc
  .tuple(uint32Boundary, uint32Boundary)
  .map(([seq, ref]) => authFields(seq, ref));

/** Keys are random but never printed: the reporter only shows domain fields. */
const keyArb = fc.uint8Array({ minLength: 1, maxLength: 64 });

describe('P9 property: decode(encode(x)) == x', () => {
  it(`test_p9_round_trip_command_and_auth (${NUM_RUNS} runs)`, async () => {
    await fc.assert(
      fc.asyncProperty(fc.oneof(commandArb, authArb), keyArb, keyArb, async (frame, link, operator) => {
        const key = frame.frame_type === 'COMMAND' ? link : operator;
        const bytes = await encodeFrame(frame, key, signer);
        expect(bytes.length).toBe(FRAME_SIZE);
        expect(bytes[0]).toBe(0xa5);
        expect(bytes[1]).toBe(0x26);
        const crc = (bytes[32] << 8) | bytes[33];
        expect(crc).toBe(crc16CcittFalse(bytes.subarray(2, 32)));
        const decoded = await decodeFrame(bytes, { link, operator }, signer);
        expect(decoded).toEqual({ ok: true, frame });
      }),
      {
        numRuns: NUM_RUNS,
        // Never print key bytes in counterexamples; report only the frame.
        reporter: (details) => {
          if (details.failed) {
            const frame = details.counterexample?.[0];
            throw new Error(`P9 failed after ${details.numRuns} runs; frame=${JSON.stringify(frame)}; seed=${details.seed}`);
          }
        },
      },
    );
  });

  it(`test_p9_auth_canonical_zero_payload (${NUM_RUNS} runs)`, async () => {
    await fc.assert(
      fc.asyncProperty(authArb, async (frame) => {
        const bytes = await encodeFrame(frame, keys.operator, signer);
        expect([...bytes.subarray(12, 24)].every((b) => b === 0)).toBe(true);
        expect(new DataView(bytes.buffer).getUint32(8, false)).toBe(frame.ref_seq);
      }),
      { numRuns: NUM_RUNS },
    );
  });

  it('test_p9_hmac_key_is_bound_to_frame_type', async () => {
    const cmd = vectorsDoc.vectors[0].frame!;
    const signedWithOperator = await encodeFrame(cmd, keys.operator, signer);
    expect(await decodeFrame(signedWithOperator, keys, signer)).toEqual({ ok: false, reason: 'HMAC' });
  });

  it('test_p9_rejects_invalid_semantics', async () => {
    const good = fromHex(vectorsDoc.vectors[1].expected_hex!);
    const bad = good.slice();
    bad[13] = 37; // AUTH verb must be 0
    const crc = crc16CcittFalse(bad.subarray(2, 32));
    bad[32] = crc >> 8;
    bad[33] = crc & 0xff;
    expect(await decodeFrame(bad, keys, signer)).toEqual({ ok: false, reason: 'FLAGS' });
    expect(await decodeFrame(good.subarray(0, 33), keys, signer)).toEqual({ ok: false, reason: 'LENGTH' });
  });

  it('test_p9_encoder_rejects_out_of_range', async () => {
    const base = vectorsDoc.vectors[0].frame!;
    await expect(encodeFrame({ ...base, seq: 0 }, keys.link, signer)).rejects.toThrow(/seq/);
    await expect(encodeFrame({ ...base, r1_centidegrees: 32768 }, keys.link, signer)).rejects.toThrow(/r1/);
    await expect(encodeFrame({ ...base, verb: 100 }, keys.link, signer)).rejects.toThrow(/verb/);
    await expect(encodeFrame({ ...base, ref_seq: 1 }, keys.link, signer)).rejects.toThrow(/ref_seq/);
  });
});
