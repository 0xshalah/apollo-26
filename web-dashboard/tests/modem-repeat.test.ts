import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { fromHex } from '../lib/frame';
import { DEFAULT_GAP_MS, durationMs, MAX_REPEAT, modulate } from '../lib/modem';

const REPO = path.resolve(import.meta.dirname, '..', '..');
const vectors = JSON.parse(readFileSync(path.join(REPO, 'contracts/vectors/frames.json'), 'utf8')) as {
  vectors: Array<{ expected_hex?: string }>;
};
const golden = fromHex(vectors.vectors[0].expected_hex!);

describe('repeated bursts', () => {
  it('repeat=1 is identical to the default single burst', () => {
    expect(modulate(golden, 48000, { repeat: 1 })).toEqual(modulate(golden, 48000));
  });

  it('repeat=3 sends three identical bursts separated by silence', () => {
    const single = modulate(golden, 48000);
    const triple = modulate(golden, 48000, { repeat: 3 });
    const gap = Math.round((DEFAULT_GAP_MS / 1000) * 48000);
    expect(triple.length).toBe(3 * single.length + 2 * gap);
    for (let i = 0; i < 3; i++) {
      const start = i * (single.length + gap);
      expect(triple.subarray(start, start + single.length)).toEqual(single);
      if (i < 2) {
        const silence = triple.subarray(start + single.length, start + single.length + gap);
        expect(silence.every((v) => v === 0)).toBe(true);
      }
    }
  });

  it('durationMs accounts for repeats and gaps', () => {
    const one = durationMs(golden, 48000);
    expect(durationMs(golden, 48000, { repeat: 3, gapMs: 300 })).toBeCloseTo(3 * one + 600, 6);
  });

  it('rejects out-of-range repeat counts', () => {
    expect(() => modulate(golden, 48000, { repeat: 0 })).toThrow(RangeError);
    expect(() => modulate(golden, 48000, { repeat: MAX_REPEAT + 1 })).toThrow(RangeError);
    expect(() => modulate(golden, 48000, { repeat: 1.5 })).toThrow(RangeError);
  });
});
