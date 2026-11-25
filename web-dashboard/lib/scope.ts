/**
 * Pure helpers for the tone scope. They turn one real AnalyserNode frequency
 * snapshot into bar levels; nothing here invents data.
 */

export interface ScopeBand {
  lowHz: number;
  highHz: number;
  bars: number;
  minDb: number;
  maxDb: number;
}

export const SCOPE_BAND: ScopeBand = { lowHz: 600, highHz: 2800, bars: 56, minDb: -100, maxDb: -20 };

/** Frequency of FFT bin `i` for a given sample rate and FFT size. */
export const binHz = (i: number, sampleRate: number, fftSize: number) => (i * sampleRate) / fftSize;

/** Bar index that contains frequency `hz`, or -1 outside the band. */
export function barForHz(hz: number, band: ScopeBand = SCOPE_BAND): number {
  if (hz < band.lowHz || hz >= band.highHz) return -1;
  return Math.floor(((hz - band.lowHz) / (band.highHz - band.lowHz)) * band.bars);
}

/**
 * Peak level per bar in [0, 1], from dBFS bins (`getFloatFrequencyData`).
 * Bars with no bins in range stay 0.
 */
export function scopeLevels(db: ArrayLike<number>, sampleRate: number, fftSize: number, band: ScopeBand = SCOPE_BAND) {
  const levels = new Array<number>(band.bars).fill(0);
  for (let i = 0; i < db.length; i++) {
    const bar = barForHz(binHz(i, sampleRate, fftSize), band);
    if (bar < 0) continue;
    const v = Number.isFinite(db[i]) ? (db[i] - band.minDb) / (band.maxDb - band.minDb) : 0;
    levels[bar] = Math.max(levels[bar], Math.min(1, Math.max(0, v)));
  }
  return levels;
}

export type DominantTone = 'MARK' | 'SPACE' | 'NONE';

/**
 * Which Bell-202 tone dominates the snapshot. `NONE` when neither tone is
 * clearly above the floor, so silence is never reported as a tone.
 */
export function dominantTone(
  db: ArrayLike<number>,
  sampleRate: number,
  fftSize: number,
  markHz: number,
  spaceHz: number,
  floorDb = -70,
): DominantTone {
  const peakNear = (hz: number) => {
    const centre = Math.round((hz * fftSize) / sampleRate);
    let peak = -Infinity;
    for (let i = Math.max(0, centre - 2); i <= Math.min(db.length - 1, centre + 2); i++) peak = Math.max(peak, db[i]);
    return peak;
  };
  const mark = peakNear(markHz);
  const space = peakNear(spaceHz);
  if (Math.max(mark, space) < floorDb) return 'NONE';
  return mark >= space ? 'MARK' : 'SPACE';
}
