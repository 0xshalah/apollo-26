/**
 * WebSocket event trust boundary. Every message is validated with Ajv (JSON
 * Schema 2020-12) against the normative schemas in ../contracts, bundled at
 * build time. Only `ValidatedConsoleEvent` values leave this module.
 *
 * The TypeScript types below are hand-written; tests/contracts.test.ts checks
 * their enums and required keys against the schema files to catch drift.
 */

import Ajv2020 from 'ajv/dist/2020';
import addFormats from 'ajv-formats';
import eventsSchema from '../../contracts/websocket-events.schema.json';
import telemetrySchema from '../../contracts/telemetry-frame.schema.json';

export const SERVICE_STATES = ['READY', 'DEGRADED', 'STOPPED'] as const;
export const AGC_STATES = ['READY', 'BUSY', 'ERROR'] as const;
export const FLIGHT_WATCH_STATES = ['STANDBY', 'WAITING', 'PROCESSING', 'HALTED'] as const;
export const SOURCE_KINDS = ['microphone', 'wav', 'loopback'] as const;
export const VERDICTS = ['ACCEPTED', 'REJECTED'] as const;
export const TELEMETRY_REASONS = [
  'OK', 'LENGTH', 'SYNC', 'VERSION', 'TYPE', 'CRC', 'FLAGS', 'HMAC', 'REPLAY', 'RANGE', 'STATE', 'INTERNAL',
] as const;
export const EVENT_TYPES = [
  'telemetry.frame', 'agc.state', 'audio.spectrum', 'test.summary', 'system.status',
] as const;

export type ServiceState = (typeof SERVICE_STATES)[number];
export type AgcHealth = (typeof AGC_STATES)[number];
export type FlightWatchState = (typeof FLIGHT_WATCH_STATES)[number];
export type EventType = (typeof EVENT_TYPES)[number];

export interface TelemetryFrameData {
  schema_version: '1.0';
  received_at: string;
  source: {
    kind: (typeof SOURCE_KINDS)[number];
    sample_rate_hz: 44100 | 48000;
    snr_db?: number | null;
    frequency_deviation_hz: number;
  };
  frame: {
    version: 1;
    frame_type: 'COMMAND' | 'AUTH';
    seq: number;
    ref_seq: number;
    critical: boolean;
    verb: number;
    noun: number;
    program: number;
    r1_centidegrees: number;
    r2_centidegrees: number;
    delta_v_tenths_fps: number;
    hmac_hex: string;
    crc_hex: string;
    raw_hex: string;
  } | null;
  validation: {
    length: boolean;
    sync: boolean;
    crc: boolean | null;
    hmac: boolean | null;
    sequence: boolean | null;
    range: boolean | null;
  };
  verdict: (typeof VERDICTS)[number];
  reason: (typeof TELEMETRY_REASONS)[number];
}

export interface AgcStateData {
  program: number;
  verb: number;
  noun: number;
  r1: number;
  r2: number;
  r3: number;
  lamps: { comp_acty: boolean; uplink_acty: boolean; key_rel: boolean; opr_err: boolean };
}

export interface SpectrumData {
  sample_rate_hz: 44100 | 48000;
  bin_hz: number[];
  power_db: number[];
}

export interface TestSummaryData {
  profile: string;
  passed: number;
  failed: number;
  skipped: number;
  report_path: string;
}

export interface SystemStatusData {
  daemon: ServiceState;
  audio: ServiceState;
  agc: AgcHealth;
  flight_watch: FlightWatchState;
}

interface EventBase<T extends EventType, D> {
  schema_version: '1.0';
  event_id: number;
  timestamp: string;
  type: T;
  data: D;
}

export type ValidatedConsoleEvent =
  | EventBase<'telemetry.frame', TelemetryFrameData>
  | EventBase<'agc.state', AgcStateData>
  | EventBase<'audio.spectrum', SpectrumData>
  | EventBase<'test.summary', TestSummaryData>
  | EventBase<'system.status', SystemStatusData>;

export type DiagnosticCategory = 'JSON_PARSE' | 'SCHEMA' | 'SPECTRUM_LENGTH_MISMATCH' | 'OVERSIZE';

export interface ContractDiagnostic {
  category: DiagnosticCategory;
  /** Bounded validator paths (instancePath + keyword); never the raw payload. */
  details: string[];
}

export type ParseResult =
  | { ok: true; event: ValidatedConsoleEvent }
  | { ok: false; diagnostic: ContractDiagnostic };

/** websocket-events.schema.json references "telemetry-frame.schema.json" relative to its $id. */
const TELEMETRY_REF_ID = new URL('telemetry-frame.schema.json', eventsSchema.$id).href;

const ajv = new Ajv2020({ allErrors: false, strict: false });
addFormats(ajv, ['date-time']);
ajv.addSchema({ ...telemetrySchema, $id: TELEMETRY_REF_ID });
const validateEvent = ajv.compile(eventsSchema);

export const MAX_MESSAGE_BYTES = 256 * 1024;
const MAX_DETAILS = 5;

/** Raw-message trust boundary: JSON text in, validated event or bounded diagnostic out. */
export function parseConsoleMessage(raw: unknown): ParseResult {
  if (typeof raw !== 'string') {
    return { ok: false, diagnostic: { category: 'JSON_PARSE', details: ['message is not text'] } };
  }
  if (raw.length > MAX_MESSAGE_BYTES) {
    return { ok: false, diagnostic: { category: 'OVERSIZE', details: [`length > ${MAX_MESSAGE_BYTES}`] } };
  }
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return { ok: false, diagnostic: { category: 'JSON_PARSE', details: ['invalid JSON'] } };
  }
  return validateConsoleEvent(value);
}

export function validateConsoleEvent(value: unknown): ParseResult {
  if (!validateEvent(value)) {
    const details = (validateEvent.errors ?? [])
      .slice(0, MAX_DETAILS)
      .map((e) => `${e.instancePath || '/'} ${e.keyword}`.slice(0, 120));
    return { ok: false, diagnostic: { category: 'SCHEMA', details } };
  }
  const event = value as ValidatedConsoleEvent;
  // Frontend refinement (not a schema rule): spectrum arrays must pair 1:1.
  if (event.type === 'audio.spectrum' && event.data.bin_hz.length !== event.data.power_db.length) {
    return {
      ok: false,
      diagnostic: {
        category: 'SPECTRUM_LENGTH_MISMATCH',
        details: [`bin_hz=${event.data.bin_hz.length} power_db=${event.data.power_db.length}`],
      },
    };
  }
  return { ok: true, event };
}
