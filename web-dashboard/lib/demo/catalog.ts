/**
 * Canonical DSKY planner for the browser demo. Mirrors mcp_server/planner.py and
 * reads the normative contracts/dsky-command-catalog-v1.json directly, so the key
 * sequences, encodings, and criticality rules are not retyped here. Equality with
 * the Python planner is tested against contracts/vectors/dsky-demo.json.
 */

import catalog from '../../../contracts/dsky-command-catalog-v1.json';
import type { DskyKeyName, DskyView } from './dsky';

export const CATALOG_VERSION: string = catalog.catalog_version;
export const HOLD_EXPIRY_MS: number = catalog.authorization.hold_expiry_ms;
export const INSPECTION_MAX_AGE_MS: number = catalog.execution.inspection_max_age_ms;
export const MIN_KEY_CADENCE_MS: number = catalog.execution.min_key_cadence_ms;

export const CRITICAL_REASONS = [
  'V37_WHILE_P40',
  'V34_WHILE_P40',
  'NONZERO_P40_ACTIVATION',
  'FRAME_CRITICAL_FLAG',
] as const;
export type CriticalReason = (typeof CRITICAL_REASONS)[number];

{
  const declared = new Set(catalog.criticality.rules.map((rule) => rule.id));
  if (declared.size !== CRITICAL_REASONS.length || CRITICAL_REASONS.some((id) => !declared.has(id))) {
    throw new Error('catalog criticality rules differ from the implemented policy');
  }
}

export interface DemoCommand {
  seq: number;
  critical: boolean;
  verb: number;
  noun: number;
  program: number;
  r1_centidegrees: number;
  r2_centidegrees: number;
  delta_v_tenths_fps: number;
}

type FieldName = 'program' | 'r1_centidegrees' | 'r2_centidegrees' | 'delta_v_tenths_fps';
type Token = string | { field: string; encoding: string };

export interface Postcondition {
  program: number;
  verb: number;
  noun: number;
  registers: { r1: number; r2: number; r3: number };
  required_clear_lamps: ['opr_err'];
}

export interface DemoPlan {
  frameSeq: number;
  commandId: string;
  keys: DskyKeyName[];
  postcondition: Postcondition;
  criticalReasons: CriticalReason[];
}

export type PlanResult = { ok: true; plan: DemoPlan } | { ok: false; error: 'UNSUPPORTED_COMMAND'; message: string };

const segments = catalog.segments as unknown as Record<string, Token[]>;
const encodings = catalog.field_encodings as Record<string, { min: number; max: number }>;

function fieldValue(command: DemoCommand, name: string): number {
  return command[name as FieldName];
}

function expand(token: Token, command: DemoCommand): DskyKeyName[] | string {
  if (typeof token === 'string') return [token as DskyKeyName];
  const value = fieldValue(command, token.field);
  const bounds = encodings[token.encoding];
  if (value < bounds.min || value > bounds.max) {
    return `${token.field}=${value} cannot be represented (${bounds.min}..${bounds.max})`;
  }
  if (token.encoding === 'DIGITS_2') {
    return [...String(value).padStart(2, '0')].map((d) => `DIGIT_${d}` as DskyKeyName);
  }
  const digits = [...String(Math.abs(value)).padStart(5, '0')].map((d) => `DIGIT_${d}` as DskyKeyName);
  return [value < 0 ? 'MINUS' : 'PLUS', ...digits];
}

export function planCommand(command: DemoCommand, state: DskyView): PlanResult {
  const entry = catalog.commands.find(
    (c) => c.match.verb === command.verb && c.match.noun === command.noun && c.match.program === command.program,
  );
  const pad = (n: number) => String(n).padStart(2, '0');
  if (!entry) {
    return {
      ok: false,
      error: 'UNSUPPORTED_COMMAND',
      message: `V${pad(command.verb)} N${pad(command.noun)} P${pad(command.program)} is not in catalog ${CATALOG_VERSION}`,
    };
  }
  const nonzero = entry.require_zero.filter((name) => fieldValue(command, name) !== 0);
  if (nonzero.length > 0) {
    return { ok: false, error: 'UNSUPPORTED_COMMAND', message: `${entry.id} requires zero ${nonzero.join(', ')}` };
  }
  const keys: DskyKeyName[] = [];
  for (const name of entry.segments) {
    for (const token of segments[name]) {
      const expanded = expand(token, command);
      if (typeof expanded === 'string') return { ok: false, error: 'UNSUPPORTED_COMMAND', message: expanded };
      keys.push(...expanded);
    }
  }
  const spec = entry.postcondition as {
    program: number | 'UNCHANGED';
    verb: number;
    noun: number | 'UNCHANGED';
    registers: 'UNCHANGED' | { r1: string; r2: string; r3: string };
  };
  const registers =
    spec.registers === 'UNCHANGED'
      ? { r1: state.r1, r2: state.r2, r3: state.r3 }
      : {
          r1: fieldValue(command, spec.registers.r1),
          r2: fieldValue(command, spec.registers.r2),
          r3: fieldValue(command, spec.registers.r3),
        };
  const postcondition: Postcondition = {
    program: spec.program === 'UNCHANGED' ? state.program : spec.program,
    verb: spec.verb,
    noun: spec.noun === 'UNCHANGED' ? state.noun : spec.noun,
    registers,
    required_clear_lamps: ['opr_err'],
  };
  return {
    ok: true,
    plan: {
      frameSeq: command.seq,
      commandId: entry.id,
      keys,
      postcondition,
      criticalReasons: criticalReasons(command, state, postcondition),
    },
  };
}

/** Union of independently computed reasons; the frame flag can only add. */
export function criticalReasons(command: DemoCommand, state: DskyView, post: Postcondition): CriticalReason[] {
  const p40Active = state.program === 40;
  const threshold = catalog.criticality.p40_critical_delta_v_threshold_tenths_fps;
  const reasons: CriticalReason[] = [];
  if (command.verb === 37 && p40Active) reasons.push('V37_WHILE_P40');
  if (command.verb === 34 && p40Active) reasons.push('V34_WHILE_P40');
  if (post.program === 40 && !p40Active && Math.abs(command.delta_v_tenths_fps) > threshold) {
    reasons.push('NONZERO_P40_ACTIVATION');
  }
  if (command.critical) reasons.push('FRAME_CRITICAL_FLAG');
  return reasons;
}

export function postconditionMatches(post: Postcondition, state: DskyView): boolean {
  return (
    state.program === post.program &&
    state.verb === post.verb &&
    state.noun === post.noun &&
    state.r1 === post.registers.r1 &&
    state.r2 === post.registers.r2 &&
    state.r3 === post.registers.r3 &&
    !state.opr_err
  );
}
