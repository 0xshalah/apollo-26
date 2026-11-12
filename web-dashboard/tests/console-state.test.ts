import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import {
  AUDIT_LIMIT,
  backoffDelayMs,
  consoleReducer,
  DIAGNOSTIC_LIMIT,
  initialConsoleState,
  socketUrl,
  type ConsoleState,
} from '../lib/console-state';
import { validateConsoleEvent, type ValidatedConsoleEvent } from '../lib/events';
import { fixtures, telemetryEvent } from './fixtures';

function valid(e: unknown): ValidatedConsoleEvent {
  const r = validateConsoleEvent(e);
  if (!r.ok) throw new Error(JSON.stringify(r.diagnostic));
  return r.event;
}

const connected = (s: ConsoleState = initialConsoleState) => consoleReducer(s, { type: 'connected', at: 't' });

describe('console reducer', () => {
  it('starts in loading for every panel', () => {
    const s = initialConsoleState;
    expect([s.agc.kind, s.spectrum.kind, s.system.kind, s.tests.kind]).toEqual(['loading', 'loading', 'loading', 'loading']);
  });

  it('routes each event only to its own panel', () => {
    let s = connected();
    s = consoleReducer(s, { type: 'event', event: valid(fixtures.agc) });
    expect(s.agc.kind).toBe('current');
    expect(s.spectrum.kind).toBe('loading');
    expect(s.audit).toHaveLength(0);
    s = consoleReducer(s, { type: 'event', event: valid(fixtures.system) });
    expect(s.system.kind).toBe('current');
    expect(s.tests.kind).toBe('loading');
  });

  it('ignores duplicate and out-of-order event ids within a connection', () => {
    let s = connected();
    s = consoleReducer(s, { type: 'event', event: valid(fixtures.system) }); // id 5
    const before = s.agc;
    s = consoleReducer(s, { type: 'event', event: valid(fixtures.agc) }); // id 2 < 5
    expect(s.agc).toBe(before);
    expect(s.ignoredOutOfOrder).toBe(1);
  });

  it('marks values stale on disconnect and resets ordering on reconnect', () => {
    let s = connected();
    s = consoleReducer(s, { type: 'event', event: valid(fixtures.system) });
    s = consoleReducer(s, { type: 'event', event: valid(telemetryEvent({}, 9)) });
    s = consoleReducer(s, { type: 'disconnected', attempt: 1, nextRetryMs: 500 });
    expect(s.system.kind).toBe('stale');
    expect(s.audit).toHaveLength(1);
    s = connected(s);
    expect(s.latestEventId).toBeNull();
    expect(s.system.kind).toBe('stale');
    s = consoleReducer(s, { type: 'event', event: valid(fixtures.agc) }); // id 2 accepted after reconnect
    expect(s.agc.kind).toBe('current');
  });

  it('flags frequency anomaly independently of the rejection reason', () => {
    let s = connected();
    s = consoleReducer(s, {
      type: 'event',
      event: valid(telemetryEvent({ source: { kind: 'wav', sample_rate_hz: 44100, frequency_deviation_hz: 50.5 } }, 1)),
    });
    s = consoleReducer(s, {
      type: 'event',
      event: valid(telemetryEvent({ source: { kind: 'wav', sample_rate_hz: 44100, frequency_deviation_hz: 50 } }, 2)),
    });
    expect(s.audit.map((r) => r.anomaly)).toEqual([true, false]);
    expect(s.audit.map((r) => r.telemetry.reason)).toEqual(['OK', 'OK']);
  });

  it('bounds audit rows and diagnostics, keeping the newest', () => {
    fc.assert(
      fc.property(fc.integer({ min: 0, max: 1200 }), fc.integer({ min: 0, max: 60 }), (rows, diags) => {
        let s = connected();
        for (let i = 1; i <= rows; i++) s = consoleReducer(s, { type: 'event', event: valid(telemetryEvent({}, i)) });
        for (let i = 0; i < diags; i++) {
          s = consoleReducer(s, { type: 'diagnostic', diagnostic: { category: 'SCHEMA', details: [String(i)] }, at: 't' });
        }
        expect(s.audit.length).toBe(Math.min(rows, AUDIT_LIMIT));
        if (rows > 0) expect(s.audit[s.audit.length - 1].eventId).toBe(rows);
        expect(s.diagnostics.length).toBe(Math.min(diags, DIAGNOSTIC_LIMIT));
        if (diags > 0) expect(s.diagnostics[s.diagnostics.length - 1].details).toEqual([String(diags - 1)]);
      }),
      { numRuns: 25 },
    );
  });
});

describe('connection helpers', () => {
  it('backoff is capped at 15 s with ±20% jitter', () => {
    fc.assert(
      fc.property(fc.integer({ min: 0, max: 40 }), fc.double({ min: 0, max: 0.9999, noNaN: true }), (attempt, r) => {
        const d = backoffDelayMs(attempt, () => r);
        const baseMs = Math.min(15000, 500 * 2 ** attempt);
        expect(d).toBeGreaterThanOrEqual(Math.floor(baseMs * 0.8));
        expect(d).toBeLessThanOrEqual(Math.ceil(baseMs * 1.2));
      }),
    );
  });

  it('derives same-origin ws/wss URLs', () => {
    expect(socketUrl({ protocol: 'http:', host: '127.0.0.1:8026' }, '/ws')).toBe('ws://127.0.0.1:8026/ws');
    expect(socketUrl({ protocol: 'https:', host: 'example.github.io' }, 'ws')).toBe('wss://example.github.io/ws');
  });
});
