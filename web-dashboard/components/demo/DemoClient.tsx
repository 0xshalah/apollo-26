'use client';

import { useCallback, useRef, useState, type ReactNode } from 'react';
import vectors from '../../../contracts/vectors/frames.json';
import { Chip, Panel, type Tone } from '@/components/Panel';
import type { DemoPlan } from '@/lib/demo/catalog';
import type { DskyKeyName, DskyView } from '@/lib/demo/dsky';
import { DemoMission } from '@/lib/demo/mission';
import { pad2, signed5 } from '@/lib/format';
import { authFields, encodeFrame, toHex, utf8, webCryptoSigner, type FrameFields } from '@/lib/frame';
import { transmitFrame } from '@/lib/modem';

interface LogEntry {
  id: number;
  actor: 'Ground' | 'Daemon' | 'Agent' | 'Gate' | 'DSKY';
  text: string;
  code: string;
  tone: Tone;
}

const BURN = { r1: 1250, r2: 420, dv: 3120 };
const WRONG_KEY = 'someone-elses-key';

const KEY_LABEL: Record<string, string> = { PLUS: '+', MINUS: '−' };
const keyLabel = (k: DskyKeyName) => KEY_LABEL[k] ?? (k.startsWith('DIGIT_') ? k.slice(6) : k);

function burnCommand(seq: number): FrameFields {
  return {
    frame_type: 'COMMAND',
    seq,
    ref_seq: 0,
    critical: true,
    verb: 37,
    noun: 0,
    program: 40,
    r1_centidegrees: BURN.r1,
    r2_centidegrees: BURN.r2,
    delta_v_tenths_fps: BURN.dv,
  };
}

function newMission() {
  const signer = webCryptoSigner(globalThis.crypto.subtle);
  const mission = new DemoMission(
    { link: utf8(vectors.demo_keys.link), operator: utf8(vectors.demo_keys.operator) },
    signer,
  );
  return { mission, signer };
}

function DemoDsky({ view, keysPressed }: { view: DskyView; keysPressed: number }) {
  const seg = (label: string, value: string) => (
    <div className="grid gap-0.5 bg-paper px-3 py-2">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="font-mono text-[1.65rem] font-medium leading-tight text-ok tabular">{value}</dd>
    </div>
  );
  const reg = (label: string, value: number) => (
    <div className="flex items-baseline justify-between gap-2 bg-paper px-3 py-2.5">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="font-mono text-[1.125rem] font-medium text-ok tabular">{signed5(value)}</dd>
    </div>
  );
  const lamp = (label: string, on: boolean) => (
    <li
      className={`flex min-h-9 items-center justify-between gap-2 rounded-pill border px-3 text-xs font-medium ${
        on ? 'border-bad bg-bad-soft text-bad' : 'border-rule bg-paper-2 text-muted'
      }`}
    >
      <span>{label}</span>
      <span className="font-mono">{on ? 'ON' : 'OFF'}</span>
    </li>
  );
  return (
    <div className="space-y-3">
      <div className="overflow-hidden rounded-card border border-rule-2 bg-rule-2">
        <dl className="grid grid-cols-3 gap-px bg-rule">
          {seg('Prog', pad2(view.program))}
          {seg('Verb', pad2(view.verb))}
          {seg('Noun', pad2(view.noun))}
        </dl>
        <dl className="mt-px grid gap-px bg-rule">
          {reg('R1 azimuth', view.r1)}
          {reg('R2 elevation', view.r2)}
          {reg('R3 delta-v', view.r3)}
        </dl>
      </div>
      <ul className="grid grid-cols-2 gap-1.5" aria-label="Lamps">
        {lamp('KEY REL', view.key_rel)}
        {lamp('OPR ERR', view.opr_err)}
      </ul>
      <p className="text-xs text-muted">
        Keys pressed by the gate this mission: <span className="font-mono text-ink tabular">{keysPressed}</span>
      </p>
    </div>
  );
}

function ActionButton({
  onClick,
  disabled,
  primary,
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  primary?: boolean;
  children: ReactNode;
}) {
  return (
    <button type="button" className={primary ? 'btn btn-amber' : 'btn'} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
}

export function DemoClient() {
  const [session, setSession] = useState(newMission);
  const [snapshot, setSnapshot] = useState(() => ({ view: session.mission.dsky.view(), keysPressed: 0 }));
  const [log, setLog] = useState<LogEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [playTones, setPlayTones] = useState(false);
  const [nextSeq, setNextSeq] = useState(1);
  const [commandSeq, setCommandSeq] = useState<number | null>(null);
  const [lastBytes, setLastBytes] = useState<Uint8Array | null>(null);
  const [plan, setPlan] = useState<DemoPlan | null>(null);
  const [inspected, setInspected] = useState(false);
  const [authSent, setAuthSent] = useState(false);
  const [executed, setExecuted] = useState(false);
  const [lastCode, setLastCode] = useState<string | null>(null);
  const idRef = useRef(0);

  const get = () => session;
  const rerender = () =>
    setSnapshot({ view: session.mission.dsky.view(), keysPressed: session.mission.keysPressed });
  const add = useCallback((entry: Omit<LogEntry, 'id'>) => {
    idRef.current += 1;
    const id = idRef.current;
    setLog((l) => [{ ...entry, id }, ...l].slice(0, 40));
  }, []);

  async function transmit(fields: FrameFields, key: string, what: string) {
    setBusy(true);
    try {
      const { mission, signer } = get();
      const bytes = await encodeFrame(fields, utf8(key), signer);
      add({ actor: 'Ground', text: `${what}, seq ${fields.seq}: ${toHex(bytes).slice(0, 24)}…`, code: 'SENT', tone: 'info' });
      if (playTones) {
        const Ctor =
          window.AudioContext ??
          (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
        const played = await transmitFrame(bytes, Ctor);
        if (played.kind === 'failed') {
          add({ actor: 'Ground', text: `Tones not played: ${played.message}`, code: played.code, tone: 'warn' });
        }
      }
      await deliver(bytes, mission);
      setLastBytes(bytes);
      return fields.seq;
    } finally {
      setBusy(false);
    }
  }

  async function deliver(bytes: Uint8Array, mission = get().mission) {
    const result = await mission.receive(bytes);
    if (result.verdict === 'REJECTED') {
      add({ actor: 'Daemon', text: 'Frame rejected; it never reaches the agent.', code: result.reason, tone: 'bad' });
    } else if (result.frame.frame_type === 'AUTH') {
      if (result.authError) {
        const why: Record<string, string> = {
          AUTH_USED: 'that COMMAND already used an AUTH or was executed',
          AUTH_EXPIRED: 'the hold window for that COMMAND has ended',
          STATE: 'no COMMAND with that sequence was delivered',
        };
        add({
          actor: 'Daemon',
          text: `AUTH seq ${result.frame.seq} is authentic, but authorizes nothing: ${why[result.authError]}.`,
          code: result.authError,
          tone: 'bad',
        });
        setLastCode(result.authError);
      } else {
        add({ actor: 'Daemon', text: `AUTH seq ${result.frame.seq} matched COMMAND ${result.authMatched}.`, code: 'ACCEPTED', tone: 'ok' });
        setLastCode('AUTH_MATCHED');
      }
    } else {
      add({ actor: 'Daemon', text: `COMMAND seq ${result.frame.seq} passed CRC, HMAC, sequence, range.`, code: 'ACCEPTED', tone: 'ok' });
    }
    rerender();
    return result;
  }

  async function sendCommand() {
    const seq = nextSeq;
    setNextSeq(seq + 1);
    await transmit(burnCommand(seq), vectors.demo_keys.link, 'P40 burn COMMAND');
    setCommandSeq(seq);
    setPlan(null);
    setInspected(false);
    setAuthSent(false);
    setExecuted(false);
    setLastCode(null);
  }

  async function sendAuth() {
    if (commandSeq === null) return;
    const seq = nextSeq;
    setNextSeq(seq + 1);
    await transmit(authFields(seq, commandSeq), vectors.demo_keys.operator, `Operator AUTH for ${commandSeq}`);
    setAuthSent(true);
  }

  async function sendForged() {
    const seq = nextSeq;
    setNextSeq(seq + 1);
    await transmit(burnCommand(seq), WRONG_KEY, 'Forged COMMAND (wrong key)');
  }

  async function replay() {
    if (!lastBytes) return;
    setBusy(true);
    try {
      add({ actor: 'Ground', text: 'Replaying the last frame, byte for byte.', code: 'SENT', tone: 'info' });
      await deliver(lastBytes);
    } finally {
      setBusy(false);
    }
  }

  function refusal(error: string, message: string) {
    add({ actor: 'Gate', text: message, code: error, tone: 'bad' });
    setLastCode(error);
    if (error === 'INSPECTION_REQUIRED' || error === 'INSPECTION_STALE') setInspected(false);
  }

  function inspect() {
    const snap = get().mission.inspect();
    setInspected(true);
    add({ actor: 'Agent', text: `inspect_agc_status: revision ${snap.revision}.`, code: 'OK', tone: 'muted' });
    rerender();
  }

  function requestPlan() {
    if (commandSeq === null) return;
    const result = get().mission.plan(commandSeq);
    if (!result.ok) {
      refusal(result.error, result.message);
      return;
    }
    setPlan(result.plan);
    setLastCode('PLANNED');
    const reasons = result.plan.criticalReasons;
    add({
      actor: 'Agent',
      text: `plan_dsky_sequence: ${result.plan.keys.length} canonical keys${reasons.length ? `, critical (${reasons.join(', ')})` : ''}.`,
      code: 'PLANNED',
      tone: 'muted',
    });
  }

  function execute(tampered: boolean) {
    if (!plan || commandSeq === null) return;
    const keys = [...plan.keys];
    if (tampered) {
      const i = keys.lastIndexOf('DIGIT_0', 30);
      keys[i >= 0 ? i : 12] = 'DIGIT_9';
    }
    add({
      actor: 'Agent',
      text: tampered ? 'execute_dsky_sequence with one digit changed.' : 'execute_dsky_sequence with the canonical keys.',
      code: 'REQUEST',
      tone: 'muted',
    });
    const result = get().mission.execute(commandSeq, keys);
    if (!result.ok) {
      refusal(result.error, result.message);
    } else if (result.idempotentReplay) {
      add({ actor: 'Gate', text: 'Already executed; no key pressed again.', code: 'IDEMPOTENT', tone: 'warn' });
      setLastCode('IDEMPOTENT');
    } else {
      add({
        actor: 'DSKY',
        text: `${result.keysPressed} keys pressed, 100 ms apart on the simulated clock; postcondition matched.`,
        code: 'EXECUTED',
        tone: 'ok',
      });
      setExecuted(true);
      setLastCode('EXECUTED');
      // The gate uses up the inspection on every allowed execution, like the MCP server.
      setInspected(false);
    }
    rerender();
  }

  function reset() {
    const fresh = newMission();
    setSession(fresh);
    setSnapshot({ view: fresh.mission.dsky.view(), keysPressed: 0 });
    setLog([]);
    setNextSeq(1);
    setCommandSeq(null);
    setLastBytes(null);
    setPlan(null);
    setInspected(false);
    setAuthSent(false);
    setExecuted(false);
    setLastCode(null);
  }

  const halted = session.mission.halted;
  const closed = lastCode === 'COMMAND_CLOSED' || lastCode === 'AUTH_EXPIRED';
  const next = halted
    ? 'Flight Watch is HALTED after a failed execution. Reset the mission.'
    : commandSeq === null
      ? 'Send the P40 burn COMMAND.'
      : closed
        ? 'This COMMAND is closed. Send a new COMMAND to start again.'
        : executed
          ? 'Done. Try a replay, a forged frame, another AUTH for the same COMMAND, or execute again.'
          : lastCode === 'AUTH_REQUIRED' && !authSent
            ? 'The gate wants an operator AUTH. Send it, then inspect, plan, and execute again.'
            : !inspected
              ? lastCode === 'INSPECTION_STALE'
                ? 'The inspection is stale. Inspect again (inspections last 20 s).'
                : 'Inspect the AGC before planning or executing.'
              : !plan
                ? 'Request the canonical plan.'
                : 'Execute the plan, or try a tampered one.';

  return (
    <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <div className="min-w-0 space-y-6">
        <div className="rounded-card border border-accent/40 bg-accent-soft p-4" role="status" aria-live="polite">
          <p className="text-xs font-medium text-accent">Next step</p>
          <p className="mt-1 text-[1.0625rem] text-ink">{next}</p>
        </div>

        <Panel id="ground" title="Ground station" aside={<Chip tone="info">Public demo keys</Chip>}>
          <p className="text-sm text-ink-2">
            P40 burn: V37 N00, R1 {signed5(BURN.r1)}, R2 {signed5(BURN.r2)}, delta-v {signed5(BURN.dv)}, CRITICAL set. Signed
            in this tab with Web Crypto.
          </p>
          <p className="mt-2 text-xs text-muted">
            In the real system the operator key lives with a human operator, apart from the link key. Here both public demo
            keys sit in this tab, so you play the operator too. Held critical commands expire after 120 s of real time.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <ActionButton primary onClick={sendCommand} disabled={busy}>
              Send COMMAND seq {nextSeq}
            </ActionButton>
            <ActionButton onClick={sendAuth} disabled={busy || commandSeq === null}>
              Send AUTH for {commandSeq ?? '—'}
            </ActionButton>
            <ActionButton onClick={replay} disabled={busy || !lastBytes}>
              Replay last frame
            </ActionButton>
            <ActionButton onClick={sendForged} disabled={busy}>
              Send forged frame
            </ActionButton>
          </div>
          <label className="mt-4 flex min-h-11 items-center gap-3 text-sm text-ink-2">
            <input
              type="checkbox"
              checked={playTones}
              onChange={(e) => setPlayTones(e.target.checked)}
              className="h-5 w-5 accent-accent"
            />
            Play each frame as Bell-202 tones (1.4 s). Validation runs on the signed bytes either way.
          </label>
        </Panel>

        <Panel id="agent" title="You are the agent" aside={<Chip tone="muted">MCP tools</Chip>}>
          <div className="flex flex-wrap gap-2">
            <ActionButton onClick={inspect} disabled={busy}>
              Inspect AGC
            </ActionButton>
            <ActionButton onClick={requestPlan} disabled={busy || commandSeq === null}>
              Request plan
            </ActionButton>
            <ActionButton primary onClick={() => execute(false)} disabled={busy || !plan}>
              Execute plan
            </ActionButton>
            <ActionButton onClick={() => execute(true)} disabled={busy || !plan}>
              Execute tampered plan
            </ActionButton>
          </div>
          {plan ? (
            <div className="mt-4">
              <p className="text-xs text-muted">
                Canonical plan for seq {plan.frameSeq} · {plan.commandId} · {plan.keys.length} keys
              </p>
              <ol className="mt-2 flex flex-wrap gap-1" aria-label="Canonical key sequence">
                {plan.keys.map((k, i) => (
                  <li key={i} className="rounded-tag border border-rule bg-paper-3 px-1.5 py-0.5 font-mono text-xs text-cool">
                    {keyLabel(k)}
                  </li>
                ))}
              </ol>
            </div>
          ) : (
            <p className="mt-4 text-sm text-muted">No plan yet. The gate only accepts the plan it computes itself.</p>
          )}
        </Panel>

        <Panel
          id="log"
          title="Daemon and gate log"
          aside={
            <button type="button" className="btn" onClick={reset} disabled={busy}>
              Reset mission
            </button>
          }
        >
          {log.length === 0 ? (
            <p className="text-sm text-muted">Nothing yet. Every frame, tool call, and gate decision appears here, newest first.</p>
          ) : (
            <ol
              className="grid max-h-[32rem] gap-px overflow-y-auto rounded-pill border border-rule bg-rule"
              tabIndex={0}
              aria-label="Log entries, newest first"
            >
              {log.map((e) => (
                <li key={e.id} className="grid grid-cols-[4.5rem_minmax(0,1fr)] items-start gap-3 bg-paper-3 px-3 py-2.5 sm:grid-cols-[4.5rem_minmax(0,1fr)_auto]">
                  <span className="text-xs font-medium text-muted">{e.actor}</span>
                  <span className="text-sm text-ink-2">{e.text}</span>
                  <span className="col-start-2 sm:col-start-auto">
                    <Chip tone={e.tone}>{e.code}</Chip>
                  </span>
                </li>
              ))}
            </ol>
          )}
        </Panel>
      </div>

      <aside aria-label="DSKY" className="order-first min-w-0 lg:sticky lg:top-4 lg:order-none lg:self-start">
        <Panel id="dsky" title="DSKY Block II (1969)" aside={<Chip tone="warn">SIMULATED</Chip>}>
          <DemoDsky view={snapshot.view} keysPressed={snapshot.keysPressed} />
        </Panel>
      </aside>
    </div>
  );
}
