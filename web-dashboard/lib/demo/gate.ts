/**
 * Safety gate for the browser demo, in the check order of mcp_server/safety_gate.py:
 * lifecycle → inspect-before-act → DSKY preconditions → canonical plan →
 * exact key equality → critical AUTH. Pure: every input is passed in.
 */

import { HOLD_EXPIRY_MS, INSPECTION_MAX_AGE_MS, planCommand, type DemoCommand, type DemoPlan } from './catalog';
import type { DskyKeyName, DskyView } from './dsky';

export type GateError =
  | 'FLIGHT_WATCH_HALTED'
  | 'EXECUTION_FAILED'
  | 'POSTCONDITION_MISMATCH'
  | 'NOT_FOUND'
  | 'IDEMPOTENCY_CONFLICT'
  | 'COMMAND_CLOSED'
  | 'INSPECTION_REQUIRED'
  | 'INSPECTION_STALE'
  | 'KEY_REL_ACTIVE'
  | 'OPR_ERR_ACTIVE'
  | 'AGC_UNAVAILABLE'
  | 'UNSUPPORTED_COMMAND'
  | 'PLAN_MISMATCH'
  | 'AUTH_REQUIRED'
  | 'AUTH_EXPIRED'
  | 'AUTH_USED';

export type CommandState = 'PENDING' | 'EXECUTED' | 'FAILED' | 'EXPIRED';
export type AuthState = 'NONE' | 'MATCHED' | 'CONSUMED';

export interface CommandRecord {
  command: DemoCommand;
  receivedAt: number;
  deliveredStep: number;
  state: CommandState;
  /** Set once a plan classified the command as critical (Python: HELD). Only held commands expire. */
  held: boolean;
  authState: AuthState;
  authSeq: number | null;
  executedKeys: DskyKeyName[] | null;
}

export interface Inspection {
  step: number;
  capturedAt: number;
  revision: number;
}

export interface Refusal {
  ok: false;
  error: GateError;
  message: string;
}

export type GateDecision =
  | { ok: true; kind: 'ALLOW'; plan: DemoPlan; authSeq: number | null }
  | { ok: true; kind: 'RECONCILE' }
  | (Refusal & { expireCommand?: boolean });

const refuse = (error: GateError, message: string): Refusal => ({ ok: false, error, message });

export function checkInspection(
  record: CommandRecord,
  inspection: Inspection | null,
  currentRevision: number,
  now: number,
): Refusal | null {
  if (!inspection || inspection.step <= record.deliveredStep) {
    return refuse('INSPECTION_REQUIRED', 'call inspect_agc_status after the COMMAND was delivered');
  }
  if (now - inspection.capturedAt >= INSPECTION_MAX_AGE_MS) {
    return refuse('INSPECTION_STALE', `inspection is ${INSPECTION_MAX_AGE_MS / 1000} s old or older; inspect again`);
  }
  if (inspection.revision !== currentRevision) {
    return refuse('INSPECTION_STALE', 'AGC state changed since inspection');
  }
  return null;
}

export function preconditionError(state: DskyView): Refusal | null {
  if (state.key_rel) return refuse('KEY_REL_ACTIVE', 'KEY REL is lit; no keys may be sent');
  if (state.opr_err) return refuse('OPR_ERR_ACTIVE', 'OPR ERR is lit; operator RSET required');
  if (state.input_state !== 'IDLE' || state.pending_entry !== null) {
    return refuse('AGC_UNAVAILABLE', 'DSKY input is mid-entry');
  }
  return null;
}

const sameKeys = (a: readonly string[], b: readonly string[]) => a.length === b.length && a.every((k, i) => k === b[i]);

export function evaluateGate(input: {
  record: CommandRecord | undefined;
  keys: DskyKeyName[];
  inspection: Inspection | null;
  current: DskyView;
  currentRevision: number;
  now: number;
  halted: boolean;
}): GateDecision {
  const { record, keys, inspection, current, currentRevision, now, halted } = input;
  if (halted) {
    return refuse('FLIGHT_WATCH_HALTED', 'Flight Watch is HALTED after a failed execution; reset the mission');
  }
  if (!record) return refuse('NOT_FOUND', 'no accepted COMMAND with that sequence');
  if (record.state === 'EXECUTED' || record.state === 'FAILED') {
    if (record.executedKeys && sameKeys(record.executedKeys, keys)) return { ok: true, kind: 'RECONCILE' };
    return refuse('IDEMPOTENCY_CONFLICT', 'this COMMAND was already claimed with a different key sequence');
  }
  if (record.state === 'EXPIRED') return refuse('COMMAND_CLOSED', `COMMAND ${record.command.seq} expired`);

  const stale = checkInspection(record, inspection, currentRevision, now);
  if (stale) return stale;
  const blocked = preconditionError(current);
  if (blocked) return blocked;

  const planned = planCommand(record.command, current);
  if (!planned.ok) return refuse(planned.error, planned.message);
  if (!sameKeys(keys, planned.plan.keys)) {
    return refuse('PLAN_MISMATCH', 'keys differ from the canonical plan; request the plan and send it unchanged');
  }

  const authSeq = record.authState === 'MATCHED' ? record.authSeq : null;
  if (planned.plan.criticalReasons.length > 0 && authSeq === null) {
    if (record.authState === 'CONSUMED') return refuse('AUTH_USED', 'AUTH for this COMMAND was already consumed');
    if (now >= record.receivedAt + HOLD_EXPIRY_MS) {
      return {
        ...refuse('AUTH_EXPIRED', `critical COMMAND held for ${HOLD_EXPIRY_MS / 1000} s without AUTH; it is now EXPIRED`),
        expireCommand: true,
      };
    }
    return refuse(
      'AUTH_REQUIRED',
      `critical command (${planned.plan.criticalReasons.join(', ')}): wait for an operator AUTH with ref_seq ${record.command.seq}, then inspect, plan, and execute again`,
    );
  }
  return { ok: true, kind: 'ALLOW', plan: planned.plan, authSeq };
}
