import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import { consoleReducer, initialConsoleState, type AuditRow } from '../lib/console-state';
import { auditStats, commandLabel, filterAudit, matchesQuery, recentVerdicts } from '../lib/console-view';
import { validateConsoleEvent } from '../lib/events';
import { telemetryEvent } from './fixtures';

const REJECTED = {
  verdict: 'REJECTED',
  reason: 'HMAC',
  validation: { length: true, sync: true, crc: true, hmac: false, sequence: null, range: null },
};

/** Builds audit rows through the real reducer from schema-valid events. */
function rowsFrom(spec: readonly { rejected: boolean; deviation: number }[]): readonly AuditRow[] {
  let s = consoleReducer(initialConsoleState, { type: 'connected', at: 't' });
  spec.forEach((item, i) => {
    const over: Record<string, unknown> = {
      source: { kind: 'loopback', sample_rate_hz: 48000, snr_db: null, frequency_deviation_hz: item.deviation },
      ...(item.rejected ? REJECTED : {}),
    };
    const r = validateConsoleEvent(telemetryEvent(over, i + 1));
    if (!r.ok) throw new Error(JSON.stringify(r.diagnostic));
    s = consoleReducer(s, { type: 'event', event: r.event });
  });
  return s.audit;
}

const specArb = fc.array(fc.record({ rejected: fc.boolean(), deviation: fc.integer({ min: 0, max: 120 }) }), {
  maxLength: 60,
});

describe('console view derivations', () => {
  it('counts verdicts and anomalies exactly', () => {
    fc.assert(
      fc.property(specArb, (spec) => {
        const rows = rowsFrom(spec);
        const s = auditStats(rows);
        expect(s.total).toBe(spec.length);
        expect(s.rejected).toBe(spec.filter((x) => x.rejected).length);
        expect(s.accepted + s.rejected).toBe(s.total);
        expect(s.anomalies).toBe(spec.filter((x) => x.deviation > 50).length);
        expect(s.latest?.eventId ?? null).toBe(spec.length > 0 ? spec.length : null);
      }),
      { numRuns: 40 },
    );
  });

  it('recentVerdicts returns the newest n verdicts, oldest first', () => {
    fc.assert(
      fc.property(specArb, fc.integer({ min: 0, max: 30 }), (spec, n) => {
        const got = recentVerdicts(rowsFrom(spec), n);
        const want = spec.slice(Math.max(0, spec.length - n)).map((x) => (x.rejected ? 'REJECTED' : 'ACCEPTED'));
        expect(got).toEqual(want);
      }),
      { numRuns: 40 },
    );
  });

  it('verdict filters partition the rows and keep newest-first order', () => {
    fc.assert(
      fc.property(specArb, (spec) => {
        const rows = rowsFrom(spec);
        const all = filterAudit(rows, { verdict: 'ALL', query: '' });
        expect(all.map((r) => r.eventId)).toEqual([...rows].reverse().map((r) => r.eventId));
        const acc = filterAudit(rows, { verdict: 'ACCEPTED', query: '' });
        const rej = filterAudit(rows, { verdict: 'REJECTED', query: '' });
        expect(acc.length + rej.length).toBe(rows.length);
        expect(acc.every((r) => r.telemetry.verdict === 'ACCEPTED')).toBe(true);
        expect(rej.every((r) => r.telemetry.verdict === 'REJECTED')).toBe(true);
      }),
      { numRuns: 40 },
    );
  });

  it('search matches event id, reason, command, and requires every term', () => {
    const rows = rowsFrom([
      { rejected: false, deviation: 10 },
      { rejected: true, deviation: 80 },
    ]);
    const [first, second] = rows;
    const cmd = commandLabel(first.telemetry.frame);
    expect(cmd).toMatch(/^V\d\d N\d\d P\d\d/);
    expect(matchesQuery(first, cmd!.toLowerCase())).toBe(true);
    expect(matchesQuery(second, 'hmac')).toBe(true);
    expect(matchesQuery(first, 'hmac')).toBe(false);
    expect(matchesQuery(second, 'tone anomaly')).toBe(true);
    expect(matchesQuery(second, '#2 rejected')).toBe(true);
    expect(matchesQuery(second, '#2 accepted')).toBe(false);
    expect(matchesQuery(second, 'EVT-2')).toBe(true);
    expect(filterAudit(rows, { verdict: 'ALL', query: '  ' })).toHaveLength(2);
  });

  it('has no command label without a decoded frame', () => {
    expect(commandLabel(null)).toBeNull();
  });
});
