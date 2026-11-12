import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  AGC_STATES,
  EVENT_TYPES,
  FLIGHT_WATCH_STATES,
  parseConsoleMessage,
  SERVICE_STATES,
  SOURCE_KINDS,
  TELEMETRY_REASONS,
  VERDICTS,
  validateConsoleEvent,
} from '../lib/events';
import { fixtures, REPO, telemetryEvent } from './fixtures';

const ev = JSON.parse(readFileSync(path.join(REPO, 'contracts/websocket-events.schema.json'), 'utf8'));
const tel = JSON.parse(readFileSync(path.join(REPO, 'contracts/telemetry-frame.schema.json'), 'utf8'));

const dataSchema = (def: string) => ev.$defs[def].allOf[1].properties.data;
const typeConst = (def: string) => ev.$defs[def].allOf[1].properties.type.const;

describe('TypeScript constants equal schema enums', () => {
  it('event types', () => {
    const defs = ev.oneOf.map((r: { $ref: string }) => r.$ref.split('/').pop());
    expect(defs.map(typeConst)).toEqual([...EVENT_TYPES]);
  });
  it('system.status enums', () => {
    const p = dataSchema('systemStatus').properties;
    expect(p.daemon.enum).toEqual([...SERVICE_STATES]);
    expect(p.audio.enum).toEqual([...SERVICE_STATES]);
    expect(p.agc.enum).toEqual([...AGC_STATES]);
    expect(p.flight_watch.enum).toEqual([...FLIGHT_WATCH_STATES]);
  });
  it('telemetry enums', () => {
    expect(tel.properties.source.properties.kind.enum).toEqual([...SOURCE_KINDS]);
    expect(tel.properties.verdict.enum).toEqual([...VERDICTS]);
    expect(tel.properties.reason.enum).toEqual([...TELEMETRY_REASONS]);
  });
});

describe('WebSocket event validation', () => {
  it('accepts every valid event variant', () => {
    for (const e of [telemetryEvent(), ...Object.values(fixtures)]) {
      const r = validateConsoleEvent(e);
      expect(r.ok, JSON.stringify(r)).toBe(true);
    }
  });

  it('accepts a rejected telemetry frame with null frame and gates', () => {
    const e = telemetryEvent({
      frame: null,
      validation: { length: true, sync: false, crc: null, hmac: null, sequence: null, range: null },
      verdict: 'REJECTED',
      reason: 'SYNC',
    });
    expect(validateConsoleEvent(e).ok).toBe(true);
  });

  it('rejects ACCEPTED with a non-OK reason (schema if/then)', () => {
    expect(validateConsoleEvent(telemetryEvent({ reason: 'CRC' })).ok).toBe(false);
  });

  it('rejects SYNC reason with a decoded frame', () => {
    expect(validateConsoleEvent(telemetryEvent({ verdict: 'REJECTED', reason: 'SYNC' })).ok).toBe(false);
  });

  it('rejects unknown type, version, extra properties, bad timestamp, out-of-schema enums', () => {
    expect(validateConsoleEvent({ ...fixtures.system, type: 'hook.status' }).ok).toBe(false);
    expect(validateConsoleEvent({ ...fixtures.system, schema_version: '2.0' }).ok).toBe(false);
    expect(validateConsoleEvent({ ...fixtures.system, extra: 1 }).ok).toBe(false);
    expect(validateConsoleEvent({ ...fixtures.system, timestamp: 'yesterday' }).ok).toBe(false);
    expect(validateConsoleEvent({ ...fixtures.system, event_id: 0 }).ok).toBe(false);
    expect(validateConsoleEvent({ ...fixtures.system, data: { ...fixtures.system.data, flight_watch: 'AUTH_WAIT' } }).ok).toBe(false);
    expect(validateConsoleEvent({ ...fixtures.agc, data: { ...fixtures.agc.data, r1: 16384 } }).ok).toBe(false);
  });

  it('rejects nested telemetry violations', () => {
    const e = telemetryEvent();
    (e.data.frame as Record<string, unknown>).raw_hex = 'zz';
    expect(validateConsoleEvent(e).ok).toBe(false);
  });

  it('rejects malformed JSON with a bounded diagnostic and no payload echo', () => {
    const r = parseConsoleMessage('{"secret":"apollo26-link-demo-key-v1"');
    expect(r).toEqual({ ok: false, diagnostic: { category: 'JSON_PARSE', details: ['invalid JSON'] } });
  });

  it('rejects non-text messages', () => {
    expect(parseConsoleMessage(new ArrayBuffer(4)).ok).toBe(false);
  });

  it('rejects unequal spectrum arrays as a frontend refinement', () => {
    const r = validateConsoleEvent({ ...fixtures.spectrum, data: { sample_rate_hz: 48000, bin_hz: [1, 2], power_db: [1] } });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.diagnostic.category).toBe('SPECTRUM_LENGTH_MISMATCH');
  });

  it('parses text messages end-to-end', () => {
    expect(parseConsoleMessage(JSON.stringify(fixtures.agc)).ok).toBe(true);
  });
});
