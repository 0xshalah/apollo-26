/**
 * Pure derivations for the console's KPI strip and audit filters.
 * Inputs are only validated AuditRows held by the reducer; nothing here invents
 * a value that no telemetry.frame event carried.
 */

import type { AuditRow } from './console-state';
import type { TelemetryFrameData } from './events';
import { pad2 } from './format';

export type Verdict = TelemetryFrameData['verdict'];
export type VerdictFilter = 'ALL' | Verdict;
export const VERDICT_FILTERS: readonly VerdictFilter[] = ['ALL', 'ACCEPTED', 'REJECTED'];

export interface AuditStats {
  total: number;
  accepted: number;
  rejected: number;
  /** Rows whose tone deviation exceeds 50 Hz (S-06), whatever the verdict. */
  anomalies: number;
  latest: AuditRow | null;
}

export function auditStats(rows: readonly AuditRow[]): AuditStats {
  let accepted = 0;
  let anomalies = 0;
  for (const r of rows) {
    if (r.telemetry.verdict === 'ACCEPTED') accepted += 1;
    if (r.anomaly) anomalies += 1;
  }
  return {
    total: rows.length,
    accepted,
    rejected: rows.length - accepted,
    anomalies,
    latest: rows.length > 0 ? rows[rows.length - 1] : null,
  };
}

/** Verdicts of the newest `n` rows, oldest first (rows are stored oldest first). */
export function recentVerdicts(rows: readonly AuditRow[], n: number): Verdict[] {
  const count = Math.max(0, Math.floor(n));
  return rows.slice(Math.max(0, rows.length - count)).map((r) => r.telemetry.verdict);
}

/** "V25 N81 P00", plus " CRIT" when the frame carries the critical flag; null without a decoded frame. */
export function commandLabel(frame: TelemetryFrameData['frame']): string | null {
  if (frame === null) return null;
  return `V${pad2(frame.verb)} N${pad2(frame.noun)} P${pad2(frame.program)}${frame.critical ? ' CRIT' : ''}`;
}

function searchText(r: AuditRow): string {
  const t = r.telemetry;
  const f = t.frame;
  const parts = [`#${r.eventId}`, `evt-${r.eventId}`, t.verdict, t.reason, t.source.kind, t.received_at];
  if (f) parts.push(f.frame_type, `seq ${f.seq}`, String(f.seq), `ref ${f.ref_seq}`, commandLabel(f) ?? '', f.raw_hex);
  if (r.anomaly) parts.push('tone anomaly');
  return parts.join(' ').toLowerCase();
}

/** Every whitespace-separated term must appear in the row's text (case-insensitive). */
export function matchesQuery(r: AuditRow, query: string): boolean {
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (terms.length === 0) return true;
  const text = searchText(r);
  return terms.every((term) => text.includes(term));
}

/** Rows matching the verdict filter and query, newest first. */
export function filterAudit(
  rows: readonly AuditRow[],
  filter: { verdict: VerdictFilter; query: string },
): AuditRow[] {
  const out: AuditRow[] = [];
  for (let i = rows.length - 1; i >= 0; i--) {
    const r = rows[i];
    if (filter.verdict !== 'ALL' && r.telemetry.verdict !== filter.verdict) continue;
    if (!matchesQuery(r, filter.query)) continue;
    out.push(r);
  }
  return out;
}
