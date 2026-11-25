/**
 * One browser-demo mission: the daemon's frame acceptance (lib/frame.ts
 * validateFrame, contract §5 order), the command/AUTH ledger, the safety gate,
 * and the DSKY. The visitor plays the agent by calling inspect / plan / execute.
 * The clock is injected so tests can step time.
 */

import { validateFrame, type FrameFields, type FrameKeys, type HmacSigner, type RejectReason } from '../frame';
import { HOLD_EXPIRY_MS, MIN_KEY_CADENCE_MS, planCommand, postconditionMatches, type PlanResult } from './catalog';
import { Dsky, type AgcErrorCode, type DskyKeyName } from './dsky';
import {
  checkInspection,
  evaluateGate,
  preconditionError,
  type CommandRecord,
  type GateError,
  type Inspection,
} from './gate';

/** AUTH ingest outcome codes, as in mcp_server/service.py _ingest_auth. */
export type AuthError = 'STATE' | 'AUTH_USED' | 'AUTH_EXPIRED';

export type ReceiveResult =
  | { verdict: 'ACCEPTED'; frame: FrameFields; authMatched: number | null; authError: AuthError | null }
  | { verdict: 'REJECTED'; reason: RejectReason };

export type ExecuteResult =
  | {
      ok: true;
      keysPressed: number;
      postconditionMatched: boolean;
      idempotentReplay: boolean;
      authSeq: number | null;
      keyError: AgcErrorCode | null;
    }
  | { ok: false; error: GateError; message: string };

export type MissionPlanResult = PlanResult | { ok: false; error: GateError; message: string };

export class DemoMission {
  readonly accepted: Array<{ frame: FrameFields; receivedAt: number }> = [];
  keysPressed = 0;
  /** Set when an execution misses its postcondition; every later execute is refused. */
  halted = false;
  private lastAcceptedSeq = 0;
  private step = 0;
  private keyClock = 0;
  private inspection: Inspection | null = null;
  private readonly records = new Map<number, CommandRecord>();

  constructor(
    private readonly keys: FrameKeys,
    private readonly signer: HmacSigner,
    private readonly now: () => number = () => Date.now(),
    readonly dsky: Dsky = new Dsky(),
  ) {}

  /** Python _expire_if_due: a held critical COMMAND closes when the hold window ends. */
  private expireIfDue(record: CommandRecord): CommandRecord {
    // Python HELD = critical plan seen and no AUTH yet; a matched AUTH makes the command READY.
    const held = record.held && record.state === 'PENDING' && record.authState === 'NONE';
    if (held && this.now() >= record.receivedAt + HOLD_EXPIRY_MS) {
      record.state = 'EXPIRED';
    }
    return record;
  }

  /** Daemon side: validate untrusted bytes, persist the sequence, publish to the agent. */
  async receive(bytes: Uint8Array): Promise<ReceiveResult> {
    const result = await validateFrame(bytes, this.keys, this.signer, this.lastAcceptedSeq);
    if (!result.ok) return { verdict: 'REJECTED', reason: result.reason };
    const frame = result.frame;
    const receivedAt = this.now();
    this.lastAcceptedSeq = frame.seq;
    this.accepted.push({ frame, receivedAt });
    this.step += 1;
    if (frame.frame_type === 'COMMAND') {
      this.records.set(frame.seq, {
        command: {
          seq: frame.seq,
          critical: frame.critical,
          verb: frame.verb,
          noun: frame.noun,
          program: frame.program,
          r1_centidegrees: frame.r1_centidegrees,
          r2_centidegrees: frame.r2_centidegrees,
          delta_v_tenths_fps: frame.delta_v_tenths_fps,
        },
        receivedAt,
        deliveredStep: this.step,
        state: 'PENDING',
        held: false,
        authState: 'NONE',
        authSeq: null,
        executedKeys: null,
      });
      return { verdict: 'ACCEPTED', frame, authMatched: null, authError: null };
    }
    const authError = this.ingestAuth(frame, receivedAt);
    return { verdict: 'ACCEPTED', frame, authMatched: authError ? null : frame.ref_seq, authError };
  }

  /** The AUTH frame itself is accepted (sequence persisted); binding it may still fail. */
  private ingestAuth(frame: FrameFields, receivedAt: number): AuthError | null {
    const found = this.records.get(frame.ref_seq);
    if (!found) return 'STATE';
    const target = this.expireIfDue(found);
    if (target.state === 'EXPIRED') return 'AUTH_EXPIRED';
    if (target.state !== 'PENDING' || target.authState !== 'NONE') return 'AUTH_USED';
    if (receivedAt >= target.receivedAt + HOLD_EXPIRY_MS) {
      if (target.held) target.state = 'EXPIRED';
      return 'AUTH_EXPIRED';
    }
    target.authState = 'MATCHED';
    target.authSeq = frame.seq;
    return null;
  }

  /** Agent tool inspect_agc_status. */
  inspect(): Inspection {
    this.step += 1;
    this.inspection = { step: this.step, capturedAt: this.now(), revision: this.dsky.revision };
    return this.inspection;
  }

  /** Agent tool plan_dsky_sequence: needs a fresh inspection, like the MCP server. */
  plan(seq: number): MissionPlanResult {
    const found = this.records.get(seq);
    if (!found) return { ok: false, error: 'NOT_FOUND', message: `no accepted COMMAND with seq ${seq}` };
    const record = this.expireIfDue(found);
    if (record.state !== 'PENDING') {
      return { ok: false, error: 'COMMAND_CLOSED', message: `COMMAND ${seq} is ${record.state}` };
    }
    const stale = checkInspection(record, this.inspection, this.dsky.revision, this.now());
    if (stale) return stale;
    const blocked = preconditionError(this.dsky.view());
    if (blocked) return blocked;
    const result = planCommand(record.command, this.dsky.view());
    if (result.ok && result.plan.criticalReasons.length > 0) record.held = true;
    return result;
  }

  /** Agent tool execute_dsky_sequence: the gate decides; only canonical keys reach the DSKY. */
  execute(seq: number, keys: DskyKeyName[]): ExecuteResult {
    const found = this.records.get(seq);
    const record = found ? this.expireIfDue(found) : undefined;
    const decision = evaluateGate({
      record,
      keys,
      inspection: this.inspection,
      current: this.dsky.view(),
      currentRevision: this.dsky.revision,
      now: this.now(),
      halted: this.halted,
    });
    if (!decision.ok) {
      if ('expireCommand' in decision && decision.expireCommand && record) record.state = 'EXPIRED';
      return { ok: false, error: decision.error, message: decision.message };
    }
    if (decision.kind === 'RECONCILE') {
      return {
        ok: true,
        keysPressed: 0,
        postconditionMatched: record!.state === 'EXECUTED',
        idempotentReplay: true,
        authSeq: record!.authSeq,
        keyError: null,
      };
    }
    const claimed = record!;
    claimed.executedKeys = [...decision.plan.keys];
    if (decision.authSeq !== null) claimed.authState = 'CONSUMED';
    this.inspection = null;
    let pressed = 0;
    let keyError: AgcErrorCode | null = null;
    this.keyClock = Math.max(this.keyClock + MIN_KEY_CADENCE_MS, this.now());
    for (const key of decision.plan.keys) {
      const result = this.dsky.press(key, this.keyClock);
      this.keyClock += MIN_KEY_CADENCE_MS;
      if (result.accepted) pressed += 1;
      if (!result.accepted || result.error) {
        keyError = result.error;
        break;
      }
    }
    this.keysPressed += pressed;
    const completed = keyError === null && pressed === decision.plan.keys.length;
    const matched = completed && postconditionMatches(decision.plan.postcondition, this.dsky.view());
    claimed.state = matched ? 'EXECUTED' : 'FAILED';
    if (!matched) {
      this.halted = true;
      return {
        ok: false,
        error: completed ? 'POSTCONDITION_MISMATCH' : 'EXECUTION_FAILED',
        message: `${pressed}/${decision.plan.keys.length} keys accepted${keyError ? ` (${keyError})` : ''}; the canonical postcondition was not reached. Flight Watch HALTED.`,
      };
    }
    return {
      ok: true,
      keysPressed: pressed,
      postconditionMatched: matched,
      idempotentReplay: false,
      authSeq: decision.authSeq,
      keyError,
    };
  }
}
