/**
 * Ground Station form trust boundary. Raw strings are parsed once into
 * `FrameFields`; invalid input never reaches Web Crypto or Web Audio.
 */

import { authFields, MAX_SEQ, type FrameFields } from './frame';

/** v1 command vocabulary (PRD §3.2). No other verbs are offered. */
export const COMMAND_KINDS = ['V37_P00', 'V37_P40', 'V25_N81', 'V34'] as const;
export type CommandKind = (typeof COMMAND_KINDS)[number];

export const COMMAND_LABELS: Record<CommandKind, string> = {
  V37_P00: 'V37 · change program to P00 (idle)',
  V37_P40: 'V37 · change program to P40 (SPS burn, simplified)',
  V25_N81: 'V25 N81 · load R1, R2, R3 (azimuth, elevation, delta-v)',
  V34: 'V34 · terminate',
};

/** Which kinds carry R1/R2/delta-v payload. */
export const CARRIES_PAYLOAD: Record<CommandKind, boolean> = {
  V37_P00: false,
  V37_P40: true,
  V25_N81: true,
  V34: false,
};

/**
 * Kinds whose CRITICAL flag the sender always sets. V37 and V34 are critical
 * while P40 is active and P40 activation is always critical (threshold 0); the
 * sender cannot see AGC state, so it marks them conservatively. The MCP safety
 * gate recomputes classification regardless of this flag.
 */
export const ALWAYS_CRITICAL: Record<CommandKind, boolean> = {
  V37_P00: true,
  V37_P40: true,
  V25_N81: false,
  V34: true,
};

/** AGC display register range; values outside it are wire-valid but the AGC rejects them. */
export const DISPLAY_RANGE = 16383;

export interface CommandFormInput {
  kind: CommandKind;
  seq: string;
  r1: string;
  r2: string;
  deltaV: string;
  extraCritical: boolean;
}

export interface AuthFormInput {
  seq: string;
  refSeq: string;
}

export type FieldErrors = Partial<Record<'seq' | 'refSeq' | 'r1' | 'r2' | 'deltaV' | 'kind', string>>;

export type ParseOutcome =
  | { ok: true; fields: FrameFields; warnings: string[] }
  | { ok: false; errors: FieldErrors };

const INT_RE = /^[+-]?\d+$/;

function parseInt32Field(raw: string, min: number, max: number, label: string): number | string {
  const t = raw.trim();
  if (t === '') return `${label} is required.`;
  if (!INT_RE.test(t)) return `${label} must be a whole number (no decimals or units).`;
  const v = Number(t);
  if (!Number.isSafeInteger(v) || v < min || v > max) return `${label} must be between ${min} and ${max}.`;
  return v;
}

export function parseCommandForm(input: CommandFormInput): ParseOutcome {
  const errors: FieldErrors = {};
  const warnings: string[] = [];
  if (!(COMMAND_KINDS as readonly string[]).includes(input.kind)) errors.kind = 'Unsupported command.';
  const seq = parseInt32Field(input.seq, 1, MAX_SEQ, 'Sequence');
  if (typeof seq === 'string') errors.seq = seq;

  let r1 = 0;
  let r2 = 0;
  let dv = 0;
  if (CARRIES_PAYLOAD[input.kind]) {
    const p1 = parseInt32Field(input.r1, -32768, 32767, 'R1');
    const p2 = parseInt32Field(input.r2, -32768, 32767, 'R2');
    const p3 = parseInt32Field(input.deltaV, -2147483648, 2147483647, 'Delta-v');
    if (typeof p1 === 'string') errors.r1 = p1;
    else r1 = p1;
    if (typeof p2 === 'string') errors.r2 = p2;
    else r2 = p2;
    if (typeof p3 === 'string') errors.deltaV = p3;
    else dv = p3;
    for (const [name, v] of [['R1', r1], ['R2', r2], ['R3 (delta-v)', dv]] as const) {
      if (Math.abs(v) > DISPLAY_RANGE) {
        warnings.push(`${name} ${v} is outside the AGC display range ±${DISPLAY_RANGE}; the emulator will reject it.`);
      }
    }
  }
  if (Object.keys(errors).length > 0 || typeof seq === 'string') return { ok: false, errors };

  const base = { frame_type: 'COMMAND' as const, seq, ref_seq: 0, r1_centidegrees: r1, r2_centidegrees: r2, delta_v_tenths_fps: dv };
  const critical = ALWAYS_CRITICAL[input.kind] || input.extraCritical;
  switch (input.kind) {
    case 'V37_P00':
      return { ok: true, warnings, fields: { ...base, critical, verb: 37, noun: 0, program: 0 } };
    case 'V37_P40':
      return { ok: true, warnings, fields: { ...base, critical, verb: 37, noun: 0, program: 40 } };
    case 'V25_N81':
      return { ok: true, warnings, fields: { ...base, critical, verb: 25, noun: 81, program: 0 } };
    case 'V34':
      return { ok: true, warnings, fields: { ...base, critical, verb: 34, noun: 0, program: 0 } };
  }
}

export function parseAuthForm(input: AuthFormInput): ParseOutcome {
  const errors: FieldErrors = {};
  const seq = parseInt32Field(input.seq, 1, MAX_SEQ, 'Sequence');
  const ref = parseInt32Field(input.refSeq, 1, MAX_SEQ, 'Referenced COMMAND sequence');
  if (typeof seq === 'string') errors.seq = seq;
  if (typeof ref === 'string') errors.refSeq = ref;
  if (typeof seq === 'number' && typeof ref === 'number' && seq <= ref) {
    errors.seq = 'AUTH sequence must be greater than the referenced COMMAND sequence.';
  }
  if (Object.keys(errors).length > 0 || typeof seq === 'string' || typeof ref === 'string') {
    return { ok: false, errors };
  }
  return { ok: true, warnings: [], fields: authFields(seq, ref) };
}

/** Non-authoritative convenience: last seq transmitted from this browser. */
export const SEQ_STORAGE_KEY = 'apollo26.ground.lastTransmittedSeq';

export function parseStoredSeq(raw: string | null): number | null {
  if (raw === null || !/^\d+$/.test(raw)) return null;
  const v = Number(raw);
  return Number.isSafeInteger(v) && v >= 1 && v <= MAX_SEQ ? v : null;
}
