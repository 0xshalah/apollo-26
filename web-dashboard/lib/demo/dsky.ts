/**
 * DSKY key handling for the browser demo, ported from agc_core/agc_engine.py
 * (VERB/NOUN/data entry, V25 N81, V34, V37 P00/P40, OPR ERR latch, KEY REL,
 * key cadence). Registers are the signed values the daemon's RPC snapshot
 * exposes, not 15-bit words. Behavior is checked against
 * contracts/vectors/dsky-demo.json, generated from the Python engine.
 */

import catalog from '../../../contracts/dsky-command-catalog-v1.json';

export type DskyKeyName =
  | 'VERB' | 'NOUN' | 'PLUS' | 'MINUS' | 'ENTR' | 'PRO' | 'CLR' | 'RSET' | 'KEY_REL'
  | 'DIGIT_0' | 'DIGIT_1' | 'DIGIT_2' | 'DIGIT_3' | 'DIGIT_4'
  | 'DIGIT_5' | 'DIGIT_6' | 'DIGIT_7' | 'DIGIT_8' | 'DIGIT_9';

export const DSKY_KEYS = catalog.keys as DskyKeyName[];

export type InputState = 'IDLE' | 'VERB_ENTRY' | 'NOUN_ENTRY' | 'DATA_ENTRY' | 'OPR_ERR';
type EntryKind = 'VERB' | 'NOUN' | 'PROGRAM' | 'V25_NOUN' | 'R1' | 'R2' | 'R3';

export type AgcErrorCode =
  | 'KEY_REL_ACTIVE'
  | 'KEY_CADENCE'
  | 'TIME_REGRESSION'
  | 'INVALID_KEY_SEQUENCE'
  | 'OPR_ERR_LATCHED'
  | 'UNSUPPORTED_VERB'
  | 'UNSUPPORTED_NOUN'
  | 'UNSUPPORTED_PROGRAM'
  | 'DISPLAY_RANGE';

/** Same projection as acoustic/agc_host.py AgcHost.view (RPC agcSnapshot control fields). */
export interface DskyView {
  program: number;
  verb: number;
  noun: number;
  r1: number;
  r2: number;
  r3: number;
  input_state: InputState;
  pending_entry: EntryKind | null;
  key_rel: boolean;
  opr_err: boolean;
}

export interface KeyResult {
  /** The key passed KEY REL, timing, and latch guards and was consumed. */
  accepted: boolean;
  /** Set when the key was refused, or consumed but logically invalid (OPR ERR). */
  error: AgcErrorCode | null;
}

interface Pending {
  kind: EntryKind;
  digits: number[];
  sign: 1 | -1 | null;
  staged: number[];
}

const V25_NOUN = 81;
const MAX_MAGNITUDE = 16383;
const PROGRAMS: Record<string, number> = { '00': 0, '40': 40 };

class LogicalFailure extends Error {
  constructor(readonly code: AgcErrorCode) {
    super(code);
  }
}

const fail = (code: AgcErrorCode): never => {
  throw new LogicalFailure(code);
};

const digitOf = (key: DskyKeyName): number | null => (key.startsWith('DIGIT_') ? Number(key.slice(6)) : null);

export class Dsky {
  private program = 0;
  private state: InputState = 'IDLE';
  private verbDisplay: number | null = null;
  private nounDisplay: number | null = null;
  private pending: Pending | null = null;
  private r: [number, number, number] = [0, 0, 0];
  private keyRel = false;
  private oprErr = false;
  private lastKeyMs: number | null = null;
  private rev = 0;

  /** Increments whenever the visible control state changes. */
  get revision(): number {
    return this.rev;
  }

  view(): DskyView {
    return {
      program: this.program,
      verb: this.verbDisplay ?? 0,
      noun: this.nounDisplay ?? 0,
      r1: this.r[0],
      r2: this.r[1],
      r3: this.r[2],
      input_state: this.state,
      pending_entry: this.pending?.kind ?? null,
      key_rel: this.keyRel,
      opr_err: this.oprErr,
    };
  }

  setKeyRel(active: boolean): void {
    this.mutate(() => {
      this.keyRel = active;
    });
  }

  press(key: DskyKeyName, atMs: number): KeyResult {
    if (!DSKY_KEYS.includes(key)) throw new RangeError(`unknown DSKY key ${key}`);
    if (this.keyRel) return { accepted: false, error: 'KEY_REL_ACTIVE' };
    if (!Number.isInteger(atMs) || atMs < 0) return { accepted: false, error: 'TIME_REGRESSION' };
    if (this.lastKeyMs !== null) {
      if (atMs < this.lastKeyMs) return { accepted: false, error: 'TIME_REGRESSION' };
      if (atMs - this.lastKeyMs < catalog.execution.min_key_cadence_ms) {
        return { accepted: false, error: 'KEY_CADENCE' };
      }
    }
    if (this.state === 'OPR_ERR' && key !== 'RSET') return { accepted: false, error: 'OPR_ERR_LATCHED' };
    let error: AgcErrorCode | null = null;
    this.mutate(() => {
      try {
        this.dispatch(key);
      } catch (failure) {
        if (!(failure instanceof LogicalFailure)) throw failure;
        this.state = 'OPR_ERR';
        this.oprErr = true;
        error = failure.code;
      }
    });
    this.lastKeyMs = atMs;
    return { accepted: true, error };
  }

  private mutate(change: () => void): void {
    const before = JSON.stringify(this.view());
    change();
    if (JSON.stringify(this.view()) !== before) this.rev += 1;
  }

  private dispatch(key: DskyKeyName): void {
    if (key === 'RSET') {
      this.clearTransient();
      this.oprErr = false;
      return;
    }
    if (key === 'KEY_REL') {
      this.clearTransient();
      return;
    }
    switch (this.state) {
      case 'IDLE':
        return this.dispatchIdle(key);
      case 'VERB_ENTRY':
        return this.dispatchVerb(key);
      case 'NOUN_ENTRY':
        return this.dispatchNoun(key);
      case 'DATA_ENTRY':
        return this.dispatchData(key);
      default:
        fail('INVALID_KEY_SEQUENCE');
    }
  }

  private dispatchIdle(key: DskyKeyName): void {
    if (key === 'VERB') {
      this.state = 'VERB_ENTRY';
      this.pending = { kind: 'VERB', digits: [], sign: null, staged: [] };
      return;
    }
    if (key === 'NOUN' && this.pending?.kind === 'V25_NOUN') {
      this.state = 'NOUN_ENTRY';
      this.pending = { kind: 'NOUN', digits: [], sign: null, staged: [] };
      return;
    }
    fail('INVALID_KEY_SEQUENCE');
  }

  /** Two-digit entry shared by VERB, NOUN, and V37 program; returns the value on ENTR. */
  private twoDigit(key: DskyKeyName, pending: Pending): number | null {
    const digit = digitOf(key);
    if (digit !== null) {
      if (pending.digits.length >= 2) fail('INVALID_KEY_SEQUENCE');
      this.pending = { ...pending, digits: [...pending.digits, digit] };
      return null;
    }
    if (key === 'CLR') {
      if (pending.digits.length === 0) fail('INVALID_KEY_SEQUENCE');
      this.pending = { ...pending, digits: pending.digits.slice(0, -1) };
      return null;
    }
    if (key !== 'ENTR' || pending.digits.length !== 2) fail('INVALID_KEY_SEQUENCE');
    return pending.digits[0] * 10 + pending.digits[1];
  }

  private requirePending(kind: EntryKind): Pending {
    if (!this.pending || this.pending.kind !== kind) fail('INVALID_KEY_SEQUENCE');
    return this.pending!;
  }

  private dispatchVerb(key: DskyKeyName): void {
    const verb = this.twoDigit(key, this.requirePending('VERB'));
    if (verb === null) return;
    if (verb === 25) {
      this.state = 'IDLE';
      this.pending = { kind: 'V25_NOUN', digits: [], sign: null, staged: [] };
    } else if (verb === 34) {
      this.program = 0;
      this.verbDisplay = 34;
      this.state = 'IDLE';
      this.pending = null;
    } else if (verb === 37) {
      this.state = 'DATA_ENTRY';
      this.pending = { kind: 'PROGRAM', digits: [], sign: null, staged: [] };
    } else {
      fail('UNSUPPORTED_VERB');
    }
  }

  private dispatchNoun(key: DskyKeyName): void {
    const noun = this.twoDigit(key, this.requirePending('NOUN'));
    if (noun === null) return;
    if (noun !== V25_NOUN) fail('UNSUPPORTED_NOUN');
    this.state = 'DATA_ENTRY';
    this.pending = { kind: 'R1', digits: [], sign: null, staged: [] };
  }

  private dispatchData(key: DskyKeyName): void {
    const pending = this.pending;
    if (!pending) return fail('INVALID_KEY_SEQUENCE');
    if (pending.kind === 'PROGRAM') {
      const target = this.twoDigit(key, pending);
      if (target === null) return;
      const program = PROGRAMS[String(target).padStart(2, '0')];
      if (program === undefined) fail('UNSUPPORTED_PROGRAM');
      this.program = program;
      this.verbDisplay = 37;
      this.nounDisplay = null;
      this.state = 'IDLE';
      this.pending = null;
      return;
    }
    if (pending.kind !== 'R1' && pending.kind !== 'R2' && pending.kind !== 'R3') fail('INVALID_KEY_SEQUENCE');
    this.dispatchV25Data(key, pending);
  }

  private dispatchV25Data(key: DskyKeyName, pending: Pending): void {
    if (key === 'PLUS' || key === 'MINUS') {
      if (pending.sign !== null || pending.digits.length > 0) fail('INVALID_KEY_SEQUENCE');
      this.pending = { ...pending, sign: key === 'PLUS' ? 1 : -1 };
      return;
    }
    const digit = digitOf(key);
    if (digit !== null) {
      if (pending.sign === null || pending.digits.length >= 5) fail('INVALID_KEY_SEQUENCE');
      this.pending = { ...pending, digits: [...pending.digits, digit] };
      return;
    }
    if (key === 'CLR') {
      if (pending.digits.length > 0) {
        this.pending = { ...pending, digits: pending.digits.slice(0, -1) };
        return;
      }
      if (pending.sign !== null) {
        this.pending = { ...pending, sign: null };
        return;
      }
      fail('INVALID_KEY_SEQUENCE');
    }
    const isFinal = pending.kind === 'R3';
    if (key === 'PRO' && !isFinal) fail('INVALID_KEY_SEQUENCE');
    if (key !== 'ENTR' && key !== 'PRO') fail('INVALID_KEY_SEQUENCE');
    if (pending.sign === null || pending.digits.length < 1) fail('INVALID_KEY_SEQUENCE');
    const magnitude = pending.digits.reduce((acc, d) => acc * 10 + d, 0);
    if (magnitude > MAX_MAGNITUDE) fail('DISPLAY_RANGE');
    const value = magnitude === 0 ? 0 : pending.sign! * magnitude;
    const staged = [...pending.staged, value];
    if (!isFinal) {
      this.pending = { kind: pending.kind === 'R1' ? 'R2' : 'R3', digits: [], sign: null, staged };
      return;
    }
    this.r = [staged[0], staged[1], staged[2]];
    this.verbDisplay = 25;
    this.nounDisplay = V25_NOUN;
    this.pending = null;
    this.state = 'IDLE';
  }

  private clearTransient(): void {
    this.state = 'IDLE';
    this.pending = null;
  }
}
