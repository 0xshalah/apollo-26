import { readFileSync } from 'node:fs';
import path from 'node:path';
import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import { fromHex } from '../lib/frame';
import {
  BAUD,
  byteTo8n1,
  DEFAULT_PREAMBLE_SYMBOLS,
  frameTo8n1,
  MARK_HZ,
  MIN_PREAMBLE_SYMBOLS,
  modulate,
  planSymbols,
  samplesPerSymbol,
  SPACE_HZ,
  transmitFrame,
} from '../lib/modem';

const REPO = path.resolve(import.meta.dirname, '..', '..');
const vectors = JSON.parse(readFileSync(path.join(REPO, 'contracts/vectors/frames.json'), 'utf8')) as {
  vectors: Array<{ expected_hex?: string }>;
};
const contract = readFileSync(path.join(REPO, 'contracts/acoustic-frame-v1.md'), 'utf8');
const golden = fromHex(vectors.vectors[0].expected_hex!);

describe('8N1 serialization', () => {
  it('serializes 0xA5 as start, LSB-first data, stop', () => {
    // 0xA5 = 1010_0101 → LSB first 1,0,1,0,0,1,0,1
    expect(byteTo8n1(0xa5)).toEqual([0, 1, 0, 1, 0, 0, 1, 0, 1, 1]);
  });

  it('serializes 0x26 and the 0x00/0xFF extremes', () => {
    expect(byteTo8n1(0x26)).toEqual([0, 0, 1, 1, 0, 0, 1, 0, 0, 1]);
    expect(byteTo8n1(0x00)).toEqual([0, 0, 0, 0, 0, 0, 0, 0, 0, 1]);
    expect(byteTo8n1(0xff)).toEqual([0, 1, 1, 1, 1, 1, 1, 1, 1, 1]);
  });

  it('rejects non-byte values and wrong frame sizes', () => {
    expect(() => byteTo8n1(256)).toThrow();
    expect(() => frameTo8n1(new Uint8Array(33))).toThrow();
  });

  it('every byte round-trips through its 8N1 symbols', () => {
    fc.assert(
      fc.property(fc.integer({ min: 0, max: 255 }), (b) => {
        const bits = byteTo8n1(b);
        expect(bits.length).toBe(10);
        expect(bits[0]).toBe(0);
        expect(bits[9]).toBe(1);
        const value = bits.slice(1, 9).reduce<number>((acc, bit, i) => acc | (bit << i), 0);
        expect(value).toBe(b);
      }),
    );
  });

  it('frame expands to 340 symbols in byte order', () => {
    const bits = frameTo8n1(golden);
    expect(bits.length).toBe(340);
    for (let i = 0; i < 34; i++) expect(bits.slice(i * 10, i * 10 + 10)).toEqual(byteTo8n1(golden[i]));
  });
});

describe('symbol plan', () => {
  it('has >= 250 ms mark preamble, the frame without gaps, then idle mark', () => {
    const plan = planSymbols(golden);
    expect(plan.preambleSymbols).toBe(DEFAULT_PREAMBLE_SYMBOLS);
    expect((plan.preambleSymbols / BAUD) * 1000).toBeGreaterThanOrEqual(250);
    expect([...plan.symbols.subarray(0, plan.preambleSymbols)].every((s) => s === 1)).toBe(true);
    expect([...plan.symbols.subarray(plan.preambleSymbols, plan.preambleSymbols + 340)]).toEqual(frameTo8n1(golden));
    expect([...plan.symbols.subarray(plan.preambleSymbols + 340)].every((s) => s === 1)).toBe(true);
  });

  it('refuses a preamble shorter than 250 ms', () => {
    expect(MIN_PREAMBLE_SYMBOLS).toBe(75);
    expect(() => planSymbols(golden, 74)).toThrow();
  });

  it('constants match the contract physical layer', () => {
    expect(contract).toContain(`Mark = ${MARK_HZ} Hz`);
    expect(contract).toContain(`space = ${SPACE_HZ} Hz`);
    expect(contract).toContain(`${BAUD} symbols/s`);
  });
});

/** Goertzel tone power of one symbol window (independent test oracle). */
function goertzelPower(x: Float32Array, start: number, n: number, freq: number, rate: number) {
  const w = (2 * Math.PI * freq) / rate;
  const c = 2 * Math.cos(w);
  let s1 = 0;
  let s2 = 0;
  for (let i = 0; i < n; i++) {
    const s = x[start + i] + c * s1 - s2;
    s2 = s1;
    s1 = s;
  }
  return s1 * s1 + s2 * s2 - c * s1 * s2;
}

describe('Bell-202 PCM', () => {
  for (const rate of [44100, 48000]) {
    it(`at ${rate} Hz: integral symbol length, correct sample count, tones per symbol`, () => {
      const sps = samplesPerSymbol(rate);
      expect(Number.isInteger(sps)).toBe(true);
      const plan = planSymbols(golden);
      const pcm = modulate(golden, rate);
      expect(pcm.length).toBe(plan.symbols.length * sps);
      for (let i = 0; i < plan.symbols.length; i++) {
        const mark = goertzelPower(pcm, i * sps, sps, MARK_HZ, rate);
        const space = goertzelPower(pcm, i * sps, sps, SPACE_HZ, rate);
        const decided = mark > space ? 1 : 0;
        expect(decided, `symbol ${i}`).toBe(plan.symbols[i]);
      }
    });

    it(`at ${rate} Hz: phase is continuous (no sample jump larger than one step)`, () => {
      const pcm = modulate(golden, rate, { edgeFadeMs: 0 });
      const maxStep = 0.8 * 2 * Math.sin((Math.PI * SPACE_HZ) / rate) + 1e-6;
      for (let i = 1; i < pcm.length; i++) {
        expect(Math.abs(pcm[i] - pcm[i - 1])).toBeLessThanOrEqual(maxStep);
      }
    });
  }

  it('rejects unsupported sample rates', () => {
    expect(() => modulate(golden, 22050)).toThrow();
  });
});

describe('transmitFrame adapter outcomes', () => {
  it('fails cleanly when Web Audio is unavailable', async () => {
    expect(await transmitFrame(golden, undefined)).toMatchObject({ kind: 'failed', code: 'UNAVAILABLE' });
  });

  it('plays the exact frame bytes and completes only on source ended', async () => {
    let captured: Float32Array | null = null;
    let onended: (() => void) | null = null;
    class FakeCtx {
      sampleRate = 48000;
      state = 'running';
      destination = {};
      resume = async () => undefined;
      close = async () => undefined;
      createBuffer(_c: number, len: number) {
        return { copyToChannel: (d: Float32Array) => (captured = d.slice(0, len)) };
      }
      createBufferSource() {
        const src = {
          buffer: null as unknown,
          connect: () => undefined,
          stop: () => undefined,
          set onended(fn: () => void) {
            onended = fn;
          },
          start: () => setTimeout(() => onended?.(), 0),
        };
        return src;
      }
    }
    const input = golden.slice();
    const out = await transmitFrame(input, FakeCtx as unknown as typeof AudioContext);
    expect(out.kind).toBe('completed');
    expect(captured).toEqual(modulate(golden, 48000));
  });
});
