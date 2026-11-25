/**
 * Browser demo mission: daemon acceptance + safety gate + DSKY, end to end.
 * Mirrors the abuse cases in docs/threat-model.md section 4.
 */
import { describe, expect, it } from 'vitest';
import { authFields, encodeFrame, utf8, webCryptoSigner, type FrameFields } from '../lib/frame';
import { HOLD_EXPIRY_MS, INSPECTION_MAX_AGE_MS, planCommand } from '../lib/demo/catalog';
import { Dsky } from '../lib/demo/dsky';
import { DemoMission } from '../lib/demo/mission';

const LINK = 'apollo26-link-demo-key-v1';
const OPERATOR = 'apollo26-operator-demo-key-v1';
const signer = webCryptoSigner(globalThis.crypto.subtle);

function command(seq: number, over: Partial<FrameFields> = {}): FrameFields {
  return {
    frame_type: 'COMMAND',
    seq,
    ref_seq: 0,
    critical: true,
    verb: 37,
    noun: 0,
    program: 40,
    r1_centidegrees: 1250,
    r2_centidegrees: 420,
    delta_v_tenths_fps: 3120,
    ...over,
  };
}

const sign = (f: FrameFields, key = f.frame_type === 'COMMAND' ? LINK : OPERATOR) => encodeFrame(f, utf8(key), signer);

function mission() {
  let now = 1_000_000;
  const m = new DemoMission({ link: utf8(LINK), operator: utf8(OPERATOR) }, signer, () => now);
  return { m, advance: (ms: number) => (now += ms) };
}

describe('demo mission', () => {
  it('holds a critical burn until a matching AUTH, then executes the canonical plan', async () => {
    const { m } = mission();
    expect((await m.receive(await sign(command(2)))).verdict).toBe('ACCEPTED');
    m.inspect();
    const plan = m.plan(2);
    expect(plan.ok && plan.plan.criticalReasons).toEqual(['NONZERO_P40_ACTIVATION', 'FRAME_CRITICAL_FLAG']);
    if (!plan.ok) return;
    expect(m.execute(2, plan.plan.keys)).toMatchObject({ ok: false, error: 'AUTH_REQUIRED' });
    expect(m.dsky.view().program).toBe(0);

    expect((await m.receive(await sign(authFields(3, 2))))).toMatchObject({ verdict: 'ACCEPTED', authMatched: 2 });
    m.inspect();
    const again = m.plan(2);
    if (!again.ok) throw new Error('plan failed');
    const result = m.execute(2, again.plan.keys);
    expect(result).toMatchObject({ ok: true, keysPressed: 36, postconditionMatched: true });
    expect(m.dsky.view()).toMatchObject({ program: 40, verb: 37, r1: 1250, r2: 420, r3: 3120, opr_err: false });
  });

  it('executes a non-critical V25 load without AUTH', async () => {
    const { m } = mission();
    await m.receive(await sign(command(1, { verb: 25, noun: 81, program: 0, critical: false })));
    m.inspect();
    const plan = m.plan(1);
    if (!plan.ok) throw new Error('plan failed');
    expect(plan.plan.criticalReasons).toEqual([]);
    expect(m.execute(1, plan.plan.keys)).toMatchObject({ ok: true, keysPressed: 29 });
  });

  it('refuses a tampered key sequence without pressing anything', async () => {
    const { m } = mission();
    await m.receive(await sign(command(1, { verb: 25, noun: 81, program: 0, critical: false })));
    m.inspect();
    const plan = m.plan(1);
    if (!plan.ok) throw new Error('plan failed');
    const tampered = [...plan.plan.keys];
    tampered[12] = 'DIGIT_9';
    expect(m.execute(1, tampered)).toMatchObject({ ok: false, error: 'PLAN_MISMATCH' });
    expect(m.dsky.view().r1).toBe(0);
    expect(m.keysPressed).toBe(0);
  });

  it('requires an inspection after the COMMAND was delivered, and a fresh one', async () => {
    const { m, advance } = mission();
    m.inspect();
    await m.receive(await sign(command(1, { verb: 25, noun: 81, program: 0, critical: false })));
    expect(m.plan(1)).toMatchObject({ ok: false, error: 'INSPECTION_REQUIRED' });
    m.inspect();
    advance(INSPECTION_MAX_AGE_MS);
    expect(m.plan(1)).toMatchObject({ ok: false, error: 'INSPECTION_STALE' });
  });

  it('treats an AGC change after inspection as stale', async () => {
    const { m } = mission();
    await m.receive(await sign(command(1, { verb: 25, noun: 81, program: 0, critical: false })));
    m.inspect();
    const load = m.plan(1);
    if (!load.ok) throw new Error('plan failed');
    m.dsky.setKeyRel(true);
    m.dsky.setKeyRel(false);
    expect(m.execute(1, load.plan.keys)).toMatchObject({ ok: false, error: 'INSPECTION_STALE' });
    expect(m.keysPressed).toBe(0);
  });

  it('rejects replayed and forged frames at the daemon', async () => {
    const { m } = mission();
    const bytes = await sign(command(5));
    expect((await m.receive(bytes)).verdict).toBe('ACCEPTED');
    expect(await m.receive(bytes)).toMatchObject({ verdict: 'REJECTED', reason: 'REPLAY' });
    expect(await m.receive(await sign(command(6), 'not-the-link-key'))).toMatchObject({
      verdict: 'REJECTED',
      reason: 'HMAC',
    });
    expect(m.accepted.map((r) => r.frame.seq)).toEqual([5]);
  });

  it('rejects a replayed AUTH frame and never presses keys twice', async () => {
    const { m } = mission();
    await m.receive(await sign(command(2)));
    const auth = await sign(authFields(3, 2));
    await m.receive(auth);
    m.inspect();
    const plan = m.plan(2);
    if (!plan.ok) throw new Error('plan failed');
    expect(m.execute(2, plan.plan.keys)).toMatchObject({ ok: true });
    expect(await m.receive(auth)).toMatchObject({ verdict: 'REJECTED', reason: 'REPLAY' });
    expect(m.execute(2, plan.plan.keys)).toMatchObject({ ok: true, idempotentReplay: true, keysPressed: 0 });
    expect(m.keysPressed).toBe(36);
  });

  it('reports an AUTH for an unknown COMMAND as STATE', async () => {
    const { m } = mission();
    expect(await m.receive(await sign(authFields(3, 99)))).toMatchObject({
      verdict: 'ACCEPTED',
      authMatched: null,
      authError: 'STATE',
    });
  });

  it('refuses a second AUTH for a COMMAND that already used one (AUTH_USED)', async () => {
    const { m } = mission();
    await m.receive(await sign(command(2)));
    expect(await m.receive(await sign(authFields(3, 2)))).toMatchObject({ authMatched: 2, authError: null });
    expect(await m.receive(await sign(authFields(4, 2)))).toMatchObject({ authMatched: null, authError: 'AUTH_USED' });
    m.inspect();
    const plan = m.plan(2);
    if (!plan.ok) throw new Error('plan failed');
    m.execute(2, plan.plan.keys);
    expect(await m.receive(await sign(authFields(5, 2)))).toMatchObject({ authMatched: null, authError: 'AUTH_USED' });
  });

  it('refuses a late AUTH and expires the held COMMAND', async () => {
    const { m, advance } = mission();
    await m.receive(await sign(command(2)));
    m.inspect();
    expect(m.plan(2).ok).toBe(true);
    advance(HOLD_EXPIRY_MS);
    expect(await m.receive(await sign(authFields(3, 2)))).toMatchObject({ authMatched: null, authError: 'AUTH_EXPIRED' });
    m.inspect();
    expect(m.plan(2)).toMatchObject({ ok: false, error: 'COMMAND_CLOSED' });
  });

  it('uses up the inspection after an execution', async () => {
    const { m } = mission();
    await m.receive(await sign(command(1, { verb: 25, noun: 81, program: 0, critical: false })));
    m.inspect();
    const plan = m.plan(1);
    if (!plan.ok) throw new Error('plan failed');
    m.execute(1, plan.plan.keys);
    expect(m.execute(1, ['VERB'])).toMatchObject({ ok: false, error: 'IDEMPOTENCY_CONFLICT' });
    await m.receive(await sign(command(2, { verb: 25, noun: 81, program: 0, critical: false, r1_centidegrees: 7 })));
    expect(m.plan(2)).toMatchObject({ ok: false, error: 'INSPECTION_REQUIRED' });
  });

  it('halts Flight Watch when the postcondition is not reached, then refuses every execute', async () => {
    class FlakyDsky extends Dsky {
      private n = 0;
      override press(key: Parameters<Dsky['press']>[0], at: number) {
        this.n += 1;
        return this.n === 10 ? { accepted: false, error: 'KEY_REL_ACTIVE' as const } : super.press(key, at);
      }
    }
    let now = 1_000_000;
    const m = new DemoMission({ link: utf8(LINK), operator: utf8(OPERATOR) }, signer, () => now, new FlakyDsky());
    await m.receive(await sign(command(1, { verb: 25, noun: 81, program: 0, critical: false })));
    await m.receive(await sign(command(2, { verb: 25, noun: 81, program: 0, critical: false, r1_centidegrees: 9 })));
    m.inspect();
    const plan = m.plan(1);
    if (!plan.ok) throw new Error('plan failed');
    expect(m.execute(1, plan.plan.keys)).toMatchObject({ ok: false, error: 'EXECUTION_FAILED' });
    expect(m.halted).toBe(true);
    now += 1;
    m.inspect();
    const other = m.plan(2);
    expect(m.execute(2, other.ok ? other.plan.keys : [])).toMatchObject({ ok: false, error: 'FLIGHT_WATCH_HALTED' });
  });

  it('closes a held critical command once the hold window ends (planned first, like Python HELD)', async () => {
    const { m, advance } = mission();
    await m.receive(await sign(command(2)));
    advance(HOLD_EXPIRY_MS);
    m.inspect();
    const plan = m.plan(2);
    if (!plan.ok) throw new Error('plan failed');
    expect(m.execute(2, plan.plan.keys)).toMatchObject({ ok: false, error: 'COMMAND_CLOSED' });
  });

  it('refuses an unplanned critical command with AUTH_EXPIRED after the window, then closes it', async () => {
    const { m, advance } = mission();
    await m.receive(await sign(command(2)));
    const planned = planCommand(
      { seq: 2, critical: true, verb: 37, noun: 0, program: 40, r1_centidegrees: 1250, r2_centidegrees: 420, delta_v_tenths_fps: 3120 },
      m.dsky.view(),
    );
    if (!planned.ok) throw new Error('plan failed');
    advance(HOLD_EXPIRY_MS);
    m.inspect();
    expect(m.execute(2, planned.plan.keys)).toMatchObject({ ok: false, error: 'AUTH_EXPIRED' });
    expect(m.execute(2, planned.plan.keys)).toMatchObject({ ok: false, error: 'COMMAND_CLOSED' });
  });

  it('keeps a command with a matched AUTH executable after the hold window', async () => {
    const { m, advance } = mission();
    await m.receive(await sign(command(2)));
    m.inspect();
    expect(m.plan(2).ok).toBe(true);
    await m.receive(await sign(authFields(3, 2)));
    advance(HOLD_EXPIRY_MS);
    m.inspect();
    const plan = m.plan(2);
    if (!plan.ok) throw new Error('plan failed');
    expect(m.execute(2, plan.plan.keys)).toMatchObject({ ok: true, keysPressed: 36 });
  });

  it('refuses execution while KEY REL is lit', async () => {
    const { m } = mission();
    await m.receive(await sign(command(1, { verb: 25, noun: 81, program: 0, critical: false })));
    m.inspect();
    const plan = m.plan(1);
    if (!plan.ok) throw new Error('plan failed');
    m.dsky.setKeyRel(true);
    m.inspect();
    expect(m.execute(1, plan.plan.keys)).toMatchObject({ ok: false, error: 'KEY_REL_ACTIVE' });
  });
});
