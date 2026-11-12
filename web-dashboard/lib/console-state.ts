/**
 * Pure console reducer. Accepts only validated events; raw socket data never
 * reaches this module. No timers, randomness, or browser APIs.
 */

import type {
  AgcStateData,
  ContractDiagnostic,
  SpectrumData,
  SystemStatusData,
  TelemetryFrameData,
  TestSummaryData,
  ValidatedConsoleEvent,
} from './events';

export const AUDIT_LIMIT = 500;
export const DIAGNOSTIC_LIMIT = 20;
export const ANOMALY_THRESHOLD_HZ = 50;

export type ConnectionState =
  | { kind: 'connecting'; attempt: number }
  | { kind: 'connected'; connectedAt: string }
  | { kind: 'disconnected'; attempt: number; nextRetryMs: number }
  | { kind: 'unsupported'; message: string };

export type PanelValue<T> =
  | { kind: 'loading' }
  | { kind: 'current'; value: T; eventId: number; timestamp: string }
  | { kind: 'stale'; value: T; eventId: number; timestamp: string };

export interface AuditRow {
  eventId: number;
  timestamp: string;
  telemetry: TelemetryFrameData;
  /** Frequency deviation strictly above 50 Hz (S-06). Independent of reason. */
  anomaly: boolean;
}

export interface TimedDiagnostic extends ContractDiagnostic {
  at: string;
}

export interface ConsoleState {
  connection: ConnectionState;
  latestEventId: number | null;
  agc: PanelValue<AgcStateData>;
  spectrum: PanelValue<SpectrumData>;
  system: PanelValue<SystemStatusData>;
  tests: PanelValue<TestSummaryData>;
  audit: readonly AuditRow[];
  selectedAuditEventId: number | null;
  diagnostics: readonly TimedDiagnostic[];
  ignoredOutOfOrder: number;
}

export const initialConsoleState: ConsoleState = {
  connection: { kind: 'connecting', attempt: 0 },
  latestEventId: null,
  agc: { kind: 'loading' },
  spectrum: { kind: 'loading' },
  system: { kind: 'loading' },
  tests: { kind: 'loading' },
  audit: [],
  selectedAuditEventId: null,
  diagnostics: [],
  ignoredOutOfOrder: 0,
};

export type ConsoleAction =
  | { type: 'connecting'; attempt: number }
  | { type: 'connected'; at: string }
  | { type: 'disconnected'; attempt: number; nextRetryMs: number }
  | { type: 'unsupported'; message: string }
  | { type: 'event'; event: ValidatedConsoleEvent }
  | { type: 'diagnostic'; diagnostic: ContractDiagnostic; at: string }
  | { type: 'select'; eventId: number | null };

function stale<T>(p: PanelValue<T>): PanelValue<T> {
  return p.kind === 'current' ? { ...p, kind: 'stale' } : p;
}

function current<T>(value: T, e: ValidatedConsoleEvent): PanelValue<T> {
  return { kind: 'current', value, eventId: e.event_id, timestamp: e.timestamp };
}

function markAllStale(s: ConsoleState): ConsoleState {
  return { ...s, agc: stale(s.agc), spectrum: stale(s.spectrum), system: stale(s.system), tests: stale(s.tests) };
}

export function isAnomaly(t: TelemetryFrameData): boolean {
  return t.source.frequency_deviation_hz > ANOMALY_THRESHOLD_HZ;
}

function applyEvent(s: ConsoleState, e: ValidatedConsoleEvent): ConsoleState {
  if (s.latestEventId !== null && e.event_id <= s.latestEventId) {
    return { ...s, ignoredOutOfOrder: s.ignoredOutOfOrder + 1 };
  }
  const next: ConsoleState = { ...s, latestEventId: e.event_id };
  switch (e.type) {
    case 'agc.state':
      return { ...next, agc: current(e.data, e) };
    case 'audio.spectrum':
      return { ...next, spectrum: current(e.data, e) };
    case 'system.status':
      return { ...next, system: current(e.data, e) };
    case 'test.summary':
      return { ...next, tests: current(e.data, e) };
    case 'telemetry.frame': {
      const row: AuditRow = { eventId: e.event_id, timestamp: e.timestamp, telemetry: e.data, anomaly: isAnomaly(e.data) };
      const audit = [...s.audit, row];
      const trimmed = audit.length > AUDIT_LIMIT ? audit.slice(audit.length - AUDIT_LIMIT) : audit;
      const selectionAlive =
        s.selectedAuditEventId === null || trimmed.some((r) => r.eventId === s.selectedAuditEventId);
      return { ...next, audit: trimmed, selectedAuditEventId: selectionAlive ? s.selectedAuditEventId : null };
    }
  }
}

export function consoleReducer(s: ConsoleState, a: ConsoleAction): ConsoleState {
  switch (a.type) {
    case 'connecting':
      return { ...s, connection: { kind: 'connecting', attempt: a.attempt } };
    case 'connected':
      // Ordering is connection-scoped: reset, but keep stale values until replaced.
      return { ...s, connection: { kind: 'connected', connectedAt: a.at }, latestEventId: null };
    case 'disconnected':
      return markAllStale({ ...s, connection: { kind: 'disconnected', attempt: a.attempt, nextRetryMs: a.nextRetryMs } });
    case 'unsupported':
      return markAllStale({ ...s, connection: { kind: 'unsupported', message: a.message } });
    case 'event':
      return applyEvent(s, a.event);
    case 'diagnostic': {
      const d = [...s.diagnostics, { ...a.diagnostic, at: a.at }];
      return { ...s, diagnostics: d.length > DIAGNOSTIC_LIMIT ? d.slice(d.length - DIAGNOSTIC_LIMIT) : d };
    }
    case 'select':
      return { ...s, selectedAuditEventId: a.eventId };
  }
}

/** Capped exponential backoff with ±20% jitter. `random` returns [0, 1). */
export function backoffDelayMs(attempt: number, random: () => number): number {
  const base = Math.min(15000, 500 * 2 ** Math.max(0, attempt));
  const jitter = 1 + (random() * 0.4 - 0.2);
  return Math.round(base * jitter);
}

/** Same-origin WebSocket URL for `path` (default /ws), mapping http→ws and https→wss. */
export function socketUrl(loc: { protocol: string; host: string }, path: string): string {
  const scheme = loc.protocol === 'https:' ? 'wss:' : 'ws:';
  const p = path.startsWith('/') ? path : `/${path}`;
  return `${scheme}//${loc.host}${p}`;
}
