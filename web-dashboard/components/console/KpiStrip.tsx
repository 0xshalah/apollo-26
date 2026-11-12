import type { ReactNode } from 'react';
import { Chip } from '@/components/Panel';
import { AUDIT_LIMIT, type AuditRow } from '@/lib/console-state';
import { auditStats, commandLabel, recentVerdicts } from '@/lib/console-view';

const RECENT = 20;

function Cell({ label, aside, children, note }: { label: string; aside?: ReactNode; children: ReactNode; note: ReactNode }) {
  return (
    <div className="grid min-w-0 content-start gap-2 bg-paper px-4 py-4">
      <dt className="flex min-w-0 items-center justify-between gap-2 text-xs font-medium text-muted">
        <span className="truncate">{label}</span>
        {aside}
      </dt>
      <dd className="min-w-0">
        {children}
        <p className="mt-2 text-xs text-muted">{note}</p>
      </dd>
    </div>
  );
}

function Awaiting({ disconnected }: { disconnected: boolean }) {
  return <Chip tone={disconnected ? 'bad' : 'muted'}>{disconnected ? 'DISCONNECTED' : 'AWAITING'}</Chip>;
}

const value = 'font-mono text-[1.35rem] font-medium text-ink tabular';

/** Metric ribbon (mockup .kpi-ribbon). Derived only from telemetry.frame rows received in this session. */
export function KpiStrip({ rows, disconnected }: { rows: readonly AuditRow[]; disconnected: boolean }) {
  const s = auditStats(rows);
  const recent = recentVerdicts(rows, RECENT);
  const recentRejected = recent.filter((v) => v === 'REJECTED').length;
  const last = s.latest;
  const lastFrame = last?.telemetry.frame ?? null;

  return (
    <section aria-label="Session counters">
      <dl className="grid grid-cols-1 gap-px border-b border-rule bg-rule sm:grid-cols-2 2xl:grid-cols-4">
        <Cell
          label="Frames this session"
          aside={s.total > 0 ? <Chip tone={s.rejected > 0 ? 'bad' : 'ok'}>{s.rejected > 0 ? `${s.rejected} rejected` : 'all accepted'}</Chip> : null}
          note={`Client window, newest ${AUDIT_LIMIT} rows.`}
        >
          {s.total === 0 ? (
            <Awaiting disconnected={disconnected} />
          ) : (
            <p className="flex flex-wrap items-baseline gap-x-4">
              <span>
                <span className={`${value} text-ok`}>{s.accepted}</span>
                <span className="ml-1.5 text-xs text-muted">accepted</span>
              </span>
              <span>
                <span className={`${value} ${s.rejected > 0 ? 'text-bad' : ''}`}>{s.rejected}</span>
                <span className="ml-1.5 text-xs text-muted">rejected</span>
              </span>
            </p>
          )}
        </Cell>

        <Cell
          label={`Last ${RECENT} verdicts`}
          aside={<span className="font-mono text-xs text-accent">Bell-202</span>}
          note={
            recent.length === 0
              ? 'Green cells are accepted frames, red cells are rejected.'
              : `${recent.length - recentRejected} accepted, ${recentRejected} rejected, oldest left.`
          }
        >
          {recent.length === 0 ? (
            <Awaiting disconnected={disconnected} />
          ) : (
            <ol aria-label={`Last ${recent.length} verdicts, oldest first`} className="flex h-5 gap-0.5">
              {recent.map((v, i) => (
                <li key={i} title={v} className={`h-full flex-1 rounded-[2px] ${v === 'ACCEPTED' ? 'bg-ok' : 'bg-bad'}`}>
                  <span className="sr-only">{v}</span>
                </li>
              ))}
            </ol>
          )}
        </Cell>

        <Cell
          label="Last frame"
          aside={last ? <Chip tone={last.telemetry.verdict === 'ACCEPTED' ? 'ok' : 'bad'}>{last.telemetry.verdict}</Chip> : null}
          note={last ? `${last.telemetry.reason} · ${last.telemetry.source.kind} · ${last.telemetry.received_at}` : 'No telemetry.frame event yet.'}
        >
          {last ? (
            <p className="flex flex-wrap items-baseline gap-x-2">
              <span className={value}>{lastFrame ? `#${lastFrame.seq}` : 'N/A'}</span>
              <span className="font-mono text-xs text-ink-2">
                {lastFrame ? `${lastFrame.frame_type} ${commandLabel(lastFrame)}` : 'not decoded'}
              </span>
            </p>
          ) : (
            <Awaiting disconnected={disconnected} />
          )}
        </Cell>

        <Cell
          label="Tone deviation, last frame"
          aside={last?.anomaly ? <Chip tone="warn">Tone anomaly</Chip> : <span className="font-mono text-xs text-accent">limit 50 Hz</span>}
          note={`Frames above 50 Hz this session: ${s.anomalies}.`}
        >
          {last ? (
            <p>
              <span className={value}>{last.telemetry.source.frequency_deviation_hz}</span>
              <span className="ml-1.5 text-xs text-muted">Hz</span>
            </p>
          ) : (
            <Awaiting disconnected={disconnected} />
          )}
        </Cell>
      </dl>
    </section>
  );
}
