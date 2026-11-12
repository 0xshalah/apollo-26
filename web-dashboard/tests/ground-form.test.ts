import { describe, expect, it } from 'vitest';
import { COMMAND_KINDS, parseAuthForm, parseCommandForm, parseStoredSeq } from '../lib/ground-form';

const cmd = { kind: 'V37_P40' as const, seq: '42', r1: '1250', r2: '420', deltaV: '31200', extraCritical: false };

describe('ground form parsing', () => {
  it('offers only the v1 vocabulary', () => {
    expect([...COMMAND_KINDS]).toEqual(['V37_P00', 'V37_P40', 'V25_N81', 'V34']);
  });

  it('parses V37 P40 into the golden-vector command fields', () => {
    const r = parseCommandForm(cmd);
    expect(r).toMatchObject({
      ok: true,
      fields: { frame_type: 'COMMAND', seq: 42, ref_seq: 0, critical: true, verb: 37, noun: 0, program: 40, r1_centidegrees: 1250, r2_centidegrees: 420, delta_v_tenths_fps: 31200 },
    });
  });

  it('V25 N81 carries payload; V34 and V37 P00 zero it', () => {
    expect(parseCommandForm({ ...cmd, kind: 'V25_N81' })).toMatchObject({ ok: true, fields: { verb: 25, noun: 81, critical: false } });
    expect(parseCommandForm({ ...cmd, kind: 'V34' })).toMatchObject({ ok: true, fields: { verb: 34, r1_centidegrees: 0, delta_v_tenths_fps: 0, critical: true } });
    expect(parseCommandForm({ ...cmd, kind: 'V37_P00' })).toMatchObject({ ok: true, fields: { program: 0, r2_centidegrees: 0 } });
  });

  it('rejects missing, decimal, and out-of-range values', () => {
    expect(parseCommandForm({ ...cmd, seq: '' })).toMatchObject({ ok: false, errors: { seq: expect.any(String) } });
    expect(parseCommandForm({ ...cmd, r1: '12.5' })).toMatchObject({ ok: false, errors: { r1: expect.any(String) } });
    expect(parseCommandForm({ ...cmd, r2: '32768' })).toMatchObject({ ok: false, errors: { r2: expect.any(String) } });
    expect(parseCommandForm({ ...cmd, seq: '0' })).toMatchObject({ ok: false });
    expect(parseCommandForm({ ...cmd, seq: '4294967296' })).toMatchObject({ ok: false });
  });

  it('warns but does not block values outside the AGC display range', () => {
    const r = parseCommandForm({ ...cmd, deltaV: '31200' });
    expect(r.ok && r.warnings.length).toBe(1);
  });

  it('AUTH is canonical and requires seq > ref_seq', () => {
    expect(parseAuthForm({ seq: '43', refSeq: '42' })).toMatchObject({
      ok: true,
      fields: { frame_type: 'AUTH', seq: 43, ref_seq: 42, critical: false, verb: 0, noun: 0, program: 0, r1_centidegrees: 0, r2_centidegrees: 0, delta_v_tenths_fps: 0 },
    });
    expect(parseAuthForm({ seq: '42', refSeq: '42' }).ok).toBe(false);
    expect(parseAuthForm({ seq: '43', refSeq: '0' }).ok).toBe(false);
  });

  it('stored sequence parsing is strict', () => {
    expect(parseStoredSeq('41')).toBe(41);
    expect(parseStoredSeq('abc')).toBeNull();
    expect(parseStoredSeq(null)).toBeNull();
    expect(parseStoredSeq('0')).toBeNull();
  });
});
