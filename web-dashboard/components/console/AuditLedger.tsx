'use client';

import { useId, useState } from 'react';
import { Chip } from '@/components/Panel';
import { AUDIT_LIMIT, type AuditRow, type ConnectionState } from '@/lib/console-state';
import { auditStats, commandLabel, filterAudit, VERDICT_FILTERS, type VerdictFilter } from '@/lib/console-view';
import { FIELD_LAYOUT, fromHex, parseFields } from '@/lib/frame';
import { centidegrees, hexBytes, pad2, tenthsFps } from '@/lib/format';

const FILTER_LABEL: Record<VerdictFilter, string> = { ALL: 'All', ACCEPTED: 'Accepted', REJECTED: 'Rejected' };

type Gate = boolean | null;

function GateCell({ value, label }: { value: Gate; label: string }) {
  const text = value === null ? 'N/A' : value ? 'PASS' : 'FAIL';
  return (
    <td className="px-4 py-3 font-mono text-xs">
      <span className="sr-only">{label}: </span>
      <span className={value === null ? 'text-muted' : value ? 'text-ok' : 'rounded-tag bg-bad-soft px-1.5 py-0.5 text-bad'}>
        {text}
      </span>
    </td>
  );
}

const th = 'border-b border-rule-2 bg-paper-3 px-4 py-3 text-xs font-medium text-muted';
const td = 'px-4 py-3 font-mono text-xs text-ink-2';

/** Mockup ledger card: toolbar (filters + search), then a scrollable table with a sticky first column. */
export function AuditLedger({
  rows,
  selectedId,
  onSelect,
  connection,
}: {
  rows: readonly AuditRow[];
  selectedId: number | null;
  onSelect: (id: number | null) => void;
  connection: ConnectionState;
}) {
  const [verdict, setVerdict] = useState<VerdictFilter>('ALL');
  const [query, setQuery] = useState('');
  const searchId = useId();
  const stats = auditStats(rows);
  const counts: Record<VerdictFilter, number> = { ALL: stats.total, ACCEPTED: stats.accepted, REJECTED: stats.rejected };
  const visible = filterAudit(rows, { verdict, query });
  const selected = rows.find((r) => r.eventId === selectedId) ?? null;
  const disconnected = connection.kind !== 'connected';
  const filtering = verdict !== 'ALL' || query.trim() !== '';

  return (
    <section id="audit" aria-labelledby="audit-title" className="min-w-0 scroll-mt-6 overflow-hidden rounded-card border border-rule-2 bg-paper-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3 px-4 py-4">
        <h2 id="audit-title" className="text-[1.125rem] text-ink">
          Frame audit log
        </h2>
        <div role="group" aria-label="Filter by verdict" className="seg-group">
          {VERDICT_FILTERS.map((f) => (
            <button key={f} type="button" aria-pressed={verdict === f} onClick={() => setVerdict(f)}>
              {FILTER_LABEL[f]} <span className="font-mono tabular">{counts[f]}</span>
            </button>
          ))}
        </div>
        <span className="ml-auto font-mono text-xs text-muted">
          {rows.length} rows · client window, newest {AUDIT_LIMIT} max
        </span>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-y border-rule bg-paper-3 px-4 py-3">
        <label htmlFor={searchId} className="sr-only">
          Search frames
        </label>
        <input
          id={searchId}
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search seq, reason, V25 N81, EVT-12…"
          autoComplete="off"
          className="input max-w-[22rem] font-mono"
        />
        <p role="status" aria-live="polite" className="font-mono text-xs text-muted tabular">
          {filtering ? `Showing ${visible.length} of ${rows.length}` : `${rows.length} shown`}
        </p>
      </div>

      {rows.length === 0 ? (
        <p className="px-4 py-10 text-center text-sm text-muted">
          {disconnected
            ? 'DISCONNECTED. No telemetry.frame events received in this session.'
            : 'Connected. Waiting for the first telemetry.frame event.'}
        </p>
      ) : visible.length === 0 ? (
        <p className="px-4 py-10 text-center text-sm text-muted">No frames match this filter.</p>
      ) : (
        <div className="max-h-[30rem] overflow-auto" role="region" aria-label="Frame audit table" tabIndex={0}>
          <table className="w-full min-w-[62rem] border-collapse text-left text-sm [&_td]:whitespace-nowrap [&_th]:whitespace-nowrap">
            <caption className="sr-only">Validated telemetry frames, newest first. History after reconnect may be incomplete.</caption>
            <thead className="sticky top-0 z-20">
              <tr>
                <th scope="col" className={`${th} sticky left-0 z-10 border-r border-rule text-ink`}>Event</th>
                <th scope="col" className={th}>Verdict</th>
                <th scope="col" className={th}>Reason</th>
                <th scope="col" className={th}>Type</th>
                <th scope="col" className={th}>Seq</th>
                <th scope="col" className={th}>Ref</th>
                <th scope="col" className={th}>Cmd</th>
                <th scope="col" className={th}>CRC</th>
                <th scope="col" className={th}>HMAC</th>
                <th scope="col" className={th}>Seq gate</th>
                <th scope="col" className={th}>Range</th>
                <th scope="col" className={th}>Source</th>
                <th scope="col" className={th}>SNR</th>
                <th scope="col" className={th}>Deviation</th>
                <th scope="col" className={th}>Received</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((r) => {
                const t = r.telemetry;
                const f = t.frame;
                const isSel = r.eventId === selectedId;
                return (
                  <tr
                    key={r.eventId}
                    className={`border-b border-rule transition-colors hover:bg-paper-3 ${isSel ? 'bg-cool-soft shadow-[inset_2px_0_0_var(--color-cool)]' : ''}`}
                  >
                    <th
                      scope="row"
                      className={`sticky left-0 z-10 border-r border-rule px-2 py-0.5 font-normal ${isSel ? 'bg-cool-soft' : 'bg-paper-3'}`}
                    >
                      <button
                        type="button"
                        onClick={() => onSelect(isSel ? null : r.eventId)}
                        aria-pressed={isSel}
                        aria-label={`Event ${r.eventId}, ${t.verdict} ${t.reason}. ${isSel ? 'Hide' : 'Show'} details`}
                        className="min-h-11 rounded-pill px-2 font-mono text-xs text-ink hover:text-accent"
                      >
                        EVT-{r.eventId}
                      </button>
                    </th>
                    <td className="px-4 py-3">
                      <Chip tone={t.verdict === 'ACCEPTED' ? 'ok' : 'bad'}>{t.verdict === 'ACCEPTED' ? 'Accepted' : 'Rejected'}</Chip>
                    </td>
                    <td className={td}>
                      {t.reason}
                      {r.anomaly ? (
                        <span className="ml-2">
                          <Chip tone="warn">Tone anomaly</Chip>
                        </span>
                      ) : null}
                    </td>
                    <td className={td}>{f ? f.frame_type : 'N/A'}</td>
                    <td className={`${td} tabular`}>{f ? f.seq : 'N/A'}</td>
                    <td className={`${td} tabular`}>{f ? f.ref_seq : 'N/A'}</td>
                    <td className={`${td} tabular text-ink`}>{commandLabel(f) ?? 'N/A'}</td>
                    <GateCell label="CRC" value={t.validation.crc} />
                    <GateCell label="HMAC" value={t.validation.hmac} />
                    <GateCell label="Sequence" value={t.validation.sequence} />
                    <GateCell label="Range" value={t.validation.range} />
                    <td className={td}>
                      {t.source.kind} · {t.source.sample_rate_hz}
                    </td>
                    <td className={`${td} tabular`}>
                      {typeof t.source.snr_db === 'number' ? `${t.source.snr_db} dB` : 'UNMEASURED'}
                    </td>
                    <td className={`${td} tabular`}>{t.source.frequency_deviation_hz} Hz</td>
                    <td className={td}>{t.received_at}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {selected ? <FrameDetail row={selected} /> : null}
    </section>
  );
}

function FrameDetail({ row }: { row: AuditRow }) {
  const t = row.telemetry;
  return (
    <section aria-labelledby="frame-detail-title" className="m-4 rounded-pill border border-rule bg-paper-3 p-4">
      <h3 id="frame-detail-title" className="text-sm text-ink">
        Event EVT-{row.eventId} · {t.verdict} · {t.reason}
      </h3>
      {row.anomaly ? (
        <p className="mt-2 text-xs text-accent">
          Acoustic anomaly: tone deviation {t.source.frequency_deviation_hz} Hz exceeds 50 Hz. This is reported separately from
          the validation reason{t.reason === 'CRC' ? '; the CRC check also failed.' : '.'}
        </p>
      ) : null}
      {t.reason === 'CRC' ? <p className="mt-2 text-xs font-medium text-bad">CRC-16 check failed for this frame.</p> : null}
      {t.frame === null ? (
        <p className="mt-2 text-sm text-muted">No decoded frame: validation stopped at {t.reason} before fields were decoded.</p>
      ) : (
        <FrameFieldTable rawHex={t.frame.raw_hex} />
      )}
    </section>
  );
}

function FrameFieldTable({ rawHex }: { rawHex: string }) {
  const bytes = fromHex(rawHex);
  const p = parseFields(bytes);
  const value: Record<string, string> = {
    sync: '',
    version: String(bytes[2]),
    frame_type: p.frame_type,
    seq: String(p.seq),
    ref_seq: String(p.ref_seq),
    flags: p.critical ? 'CRITICAL' : 'none',
    verb: pad2(p.verb),
    noun: pad2(p.noun),
    program: pad2(p.program),
    r1: centidegrees(p.r1_centidegrees),
    r2: centidegrees(p.r2_centidegrees),
    delta_v: tenthsFps(p.delta_v_tenths_fps),
    hmac: '',
    crc: '',
  };
  return (
    <div className="mt-3 overflow-x-auto" role="region" aria-label="Decoded frame fields" tabIndex={0}>
      <p className="break-all font-mono text-xs text-cool">{rawHex}</p>
      <table className="mt-2 w-full min-w-[30rem] border-collapse text-left text-xs">
        <thead className="text-muted">
          <tr>
            <th scope="col" className="py-1.5 pr-3 font-medium">Offset</th>
            <th scope="col" className="py-1.5 pr-3 font-medium">Field</th>
            <th scope="col" className="py-1.5 pr-3 font-medium">Bytes</th>
            <th scope="col" className="py-1.5 font-medium">Value</th>
          </tr>
        </thead>
        <tbody>
          {FIELD_LAYOUT.map((f) => (
            <tr key={f.name} className="border-t border-rule">
              <td className="py-1.5 pr-3 font-mono text-muted">{f.offset}</td>
              <th scope="row" className="py-1.5 pr-3 font-normal text-ink-2">{f.name}</th>
              <td className="py-1.5 pr-3 font-mono text-ok">{hexBytes(bytes, f.offset, f.length)}</td>
              <td className="py-1.5 font-mono text-ink-2">{value[f.name]}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
