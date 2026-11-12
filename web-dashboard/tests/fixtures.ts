import { readFileSync } from 'node:fs';
import path from 'node:path';

/** Test-only event fixtures. They are inputs to validators, never UI data. */
export const REPO = path.resolve(import.meta.dirname, '..', '..');
const vectors = JSON.parse(readFileSync(path.join(REPO, 'contracts/vectors/frames.json'), 'utf8'));
const raw = vectors.vectors[0].expected_hex as string;
const f = vectors.vectors[0].frame;
const base = { schema_version: '1.0', timestamp: '2026-11-20T10:00:00Z' };

export const telemetryEvent = (over: Record<string, unknown> = {}, eventId = 1) => ({
  ...base,
  event_id: eventId,
  type: 'telemetry.frame',
  data: {
    schema_version: '1.0',
    received_at: '2026-11-20T10:00:00Z',
    source: { kind: 'microphone', sample_rate_hz: 48000, snr_db: null, frequency_deviation_hz: 12 },
    frame: { version: 1, ...f, hmac_hex: raw.slice(48, 64), crc_hex: raw.slice(64, 68), raw_hex: raw },
    validation: { length: true, sync: true, crc: true, hmac: true, sequence: true, range: true },
    verdict: 'ACCEPTED',
    reason: 'OK',
    ...over,
  } as Record<string, unknown>,
});

export const fixtures = {
  agc: {
    ...base,
    event_id: 2,
    type: 'agc.state',
    data: { program: 40, verb: 37, noun: 0, r1: 1250, r2: 420, r3: 0, lamps: { comp_acty: true, uplink_acty: false, key_rel: false, opr_err: false } },
  },
  spectrum: { ...base, event_id: 3, type: 'audio.spectrum', data: { sample_rate_hz: 48000, bin_hz: [1200, 2200], power_db: [-20, -40] } },
  tests: { ...base, event_id: 4, type: 'test.summary', data: { profile: 'fast', passed: 10, failed: 1, skipped: 0, report_path: 'docs/pbt-report.md' } },
  system: { ...base, event_id: 5, type: 'system.status', data: { daemon: 'READY', audio: 'DEGRADED', agc: 'READY', flight_watch: 'WAITING' } },
};
