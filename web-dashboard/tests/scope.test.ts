import { describe, expect, it } from 'vitest';
import { MARK_HZ, SPACE_HZ } from '@/lib/modem';
import { barForHz, binHz, dominantTone, SCOPE_BAND, scopeLevels } from '@/lib/scope';

const RATE = 48000;
const FFT = 4096;
const BINS = FFT / 2;

function snapshot(peakHz: number | null, peakDb = -30, floorDb = -120) {
  const db = new Float32Array(BINS).fill(floorDb);
  if (peakHz !== null) db[Math.round((peakHz * FFT) / RATE)] = peakDb;
  return db;
}

describe('tone scope', () => {
  it('maps bins to the right frequency', () => {
    expect(binHz(1, RATE, FFT)).toBeCloseTo(11.71875);
  });

  it('places mark below space and rejects out-of-band frequencies', () => {
    expect(barForHz(MARK_HZ)).toBeGreaterThanOrEqual(0);
    expect(barForHz(SPACE_HZ)).toBeGreaterThan(barForHz(MARK_HZ));
    expect(barForHz(SCOPE_BAND.lowHz - 1)).toBe(-1);
    expect(barForHz(SCOPE_BAND.highHz)).toBe(-1);
  });

  it('lights only the bar that holds the played tone', () => {
    const levels = scopeLevels(snapshot(MARK_HZ), RATE, FFT);
    expect(levels).toHaveLength(SCOPE_BAND.bars);
    const lit = levels.map((v, i) => (v > 0 ? i : -1)).filter((i) => i >= 0);
    expect(lit).toEqual([barForHz(MARK_HZ)]);
  });

  it('draws silence as zero bars', () => {
    expect(scopeLevels(snapshot(null, 0, -Infinity), RATE, FFT).every((v) => v === 0)).toBe(true);
  });

  it('names the dominant tone and never reports silence as a tone', () => {
    expect(dominantTone(snapshot(MARK_HZ), RATE, FFT, MARK_HZ, SPACE_HZ)).toBe('MARK');
    expect(dominantTone(snapshot(SPACE_HZ), RATE, FFT, MARK_HZ, SPACE_HZ)).toBe('SPACE');
    expect(dominantTone(snapshot(null), RATE, FFT, MARK_HZ, SPACE_HZ)).toBe('NONE');
  });
});
