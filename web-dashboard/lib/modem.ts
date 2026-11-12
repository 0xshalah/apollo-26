/**
 * Bell-202 modulator for Apollo-26 v1 (contract §1): 300 symbols/s,
 * mark 1200 Hz = bit 1, space 2200 Hz = bit 0, continuous phase,
 * mark preamble >= 250 ms, 8N1 with LSB-first data bits.
 *
 * Pure planning/sample generation lives here; `playPcm` is the only function
 * touching Web Audio and receives its AudioContext constructor explicitly.
 */

import { FRAME_SIZE } from './frame';

export const BAUD = 300;
export const MARK_HZ = 1200;
export const SPACE_HZ = 2200;
export const SUPPORTED_SAMPLE_RATES = [44100, 48000] as const;
export type SampleRate = (typeof SUPPORTED_SAMPLE_RATES)[number];
/** 250 ms at 300 baud. Matches acoustic/modem.py MIN_PREAMBLE_SYMBOLS. */
export const MIN_PREAMBLE_SYMBOLS = 75;
/** Default preamble: 90 symbols = 300 ms (margin above the 250 ms minimum). */
export const DEFAULT_PREAMBLE_SYMBOLS = 90;
/** Idle mark after the last stop bit so the end fade never touches frame symbols. */
export const DEFAULT_TAIL_SYMBOLS = 15;
export const BITS_PER_BYTE_8N1 = 10;

export type Bit = 0 | 1;

/** One byte as 8N1: start 0, data LSB-first, stop 1. */
export function byteTo8n1(value: number): Bit[] {
  if (!Number.isInteger(value) || value < 0 || value > 255) throw new RangeError('byte 0..255');
  const bits: Bit[] = [0];
  for (let i = 0; i < 8; i++) bits.push(((value >> i) & 1) as Bit);
  bits.push(1);
  return bits;
}

/** 8N1 bitstream of the frame only (no preamble), 340 bits for 34 bytes. */
export function frameTo8n1(frame: Uint8Array): Bit[] {
  if (frame.length !== FRAME_SIZE) throw new RangeError(`frame must be ${FRAME_SIZE} bytes`);
  const bits: Bit[] = [];
  for (const b of frame) bits.push(...byteTo8n1(b));
  return bits;
}

export interface SymbolPlan {
  symbols: Uint8Array;
  preambleSymbols: number;
  frameSymbols: number;
  tailSymbols: number;
}

export function planSymbols(
  frame: Uint8Array,
  preambleSymbols: number = DEFAULT_PREAMBLE_SYMBOLS,
  tailSymbols: number = DEFAULT_TAIL_SYMBOLS,
): SymbolPlan {
  if (!Number.isInteger(preambleSymbols) || preambleSymbols < MIN_PREAMBLE_SYMBOLS) {
    throw new RangeError(`preamble must be >= ${MIN_PREAMBLE_SYMBOLS} symbols (250 ms)`);
  }
  if (!Number.isInteger(tailSymbols) || tailSymbols < 0) throw new RangeError('tail >= 0');
  const bits = frameTo8n1(frame);
  const symbols = new Uint8Array(preambleSymbols + bits.length + tailSymbols);
  symbols.fill(1, 0, preambleSymbols);
  symbols.set(bits, preambleSymbols);
  symbols.fill(1, preambleSymbols + bits.length);
  return { symbols, preambleSymbols, frameSymbols: bits.length, tailSymbols };
}

export function samplesPerSymbol(sampleRate: number): number {
  if (!(SUPPORTED_SAMPLE_RATES as readonly number[]).includes(sampleRate)) {
    throw new RangeError(`unsupported sample rate ${sampleRate}`);
  }
  return sampleRate / BAUD; // 147 or 160, integral
}

export interface ModulateOptions {
  amplitude?: number;
  preambleSymbols?: number;
  tailSymbols?: number;
  /** Fade length applied only at the very start and end of the buffer. */
  edgeFadeMs?: number;
}

/**
 * Phase-continuous FSK PCM from the real encoded frame. A single phase
 * accumulator runs across preamble, frame, and tail symbols.
 */
export function modulate(
  frame: Uint8Array,
  sampleRate: number,
  opts: ModulateOptions = {},
): Float32Array<ArrayBuffer> {
  const amplitude = opts.amplitude ?? 0.8;
  if (!(amplitude > 0 && amplitude <= 1)) throw new RangeError('amplitude in (0, 1]');
  const plan = planSymbols(frame, opts.preambleSymbols, opts.tailSymbols);
  const sps = samplesPerSymbol(sampleRate);
  const out = new Float32Array(plan.symbols.length * sps);
  const twoPi = 2 * Math.PI;
  let phase = 0;
  let n = 0;
  for (const s of plan.symbols) {
    const inc = (twoPi * (s === 1 ? MARK_HZ : SPACE_HZ)) / sampleRate;
    for (let k = 0; k < sps; k++) {
      out[n++] = amplitude * Math.sin(phase);
      phase += inc;
      if (phase >= twoPi) phase -= twoPi;
    }
  }
  const fadeMs = opts.edgeFadeMs ?? 5;
  const fade = Math.min(
    Math.floor((fadeMs / 1000) * sampleRate),
    plan.preambleSymbols * sps,
    plan.tailSymbols * sps,
  );
  for (let i = 0; i < fade; i++) {
    const g = i / fade;
    out[i] *= g;
    out[out.length - 1 - i] *= g;
  }
  return out;
}

export function durationMs(frame: Uint8Array, sampleRate: number, opts: ModulateOptions = {}) {
  const plan = planSymbols(frame, opts.preambleSymbols, opts.tailSymbols);
  return (plan.symbols.length * samplesPerSymbol(sampleRate) * 1000) / sampleRate;
}

export type TransmitOutcome =
  | { kind: 'completed'; sampleRate: number; durationMs: number }
  | { kind: 'cancelled' }
  | { kind: 'failed'; code: 'UNAVAILABLE' | 'UNSUPPORTED_RATE' | 'SUSPENDED' | 'PLAYBACK'; message: string };

type AudioContextCtor = new (options?: AudioContextOptions) => AudioContext;

/**
 * Plays the frame through Web Audio. Must be called from a user gesture.
 * Resolves `completed` only from the source `ended` event.
 */
export async function transmitFrame(
  frame: Uint8Array,
  Ctor: AudioContextCtor | undefined,
  signal?: AbortSignal,
  opts: ModulateOptions = {},
): Promise<TransmitOutcome> {
  if (!Ctor) return { kind: 'failed', code: 'UNAVAILABLE', message: 'Web Audio is not available in this browser.' };
  const bytes = frame.slice(); // immutable copy of the exact previewed bytes
  let ctx: AudioContext;
  try {
    ctx = new Ctor({ sampleRate: 48000 });
  } catch {
    try {
      ctx = new Ctor();
    } catch (e) {
      return { kind: 'failed', code: 'UNAVAILABLE', message: `Could not create AudioContext: ${String(e)}` };
    }
  }
  try {
    const rate = ctx.sampleRate;
    if (!(SUPPORTED_SAMPLE_RATES as readonly number[]).includes(rate)) {
      return { kind: 'failed', code: 'UNSUPPORTED_RATE', message: `Audio output runs at ${rate} Hz; 44100 or 48000 Hz is required.` };
    }
    if (ctx.state === 'suspended') await ctx.resume();
    if (ctx.state !== 'running') {
      return { kind: 'failed', code: 'SUSPENDED', message: 'Audio output is suspended. Tap Transmit again or check browser permissions.' };
    }
    const pcm = modulate(bytes, rate, opts);
    const buffer = ctx.createBuffer(1, pcm.length, rate);
    buffer.copyToChannel(pcm, 0);
    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(ctx.destination);
    const result = await new Promise<TransmitOutcome>((resolve) => {
      const onAbort = () => {
        try {
          src.stop();
        } catch {
          /* already stopped */
        }
        resolve({ kind: 'cancelled' });
      };
      if (signal?.aborted) return onAbort();
      signal?.addEventListener('abort', onAbort, { once: true });
      src.onended = () => {
        signal?.removeEventListener('abort', onAbort);
        if (signal?.aborted) return;
        resolve({ kind: 'completed', sampleRate: rate, durationMs: (pcm.length * 1000) / rate });
      };
      src.start();
    });
    return result;
  } catch (e) {
    return { kind: 'failed', code: 'PLAYBACK', message: `Playback failed: ${String(e)}` };
  } finally {
    void ctx.close().catch(() => undefined);
  }
}
