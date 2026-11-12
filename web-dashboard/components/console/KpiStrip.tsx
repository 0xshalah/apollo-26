import type { ReactNode } from 'react';
import { Chip } from '@/components/Panel';
import { AUDIT_LIMIT, type AuditRow } from '@/lib/console-state';
import { auditStats, commandLabel, recentVerdicts } from '@/lib/console-view';

const RECENT = 20;

function Cell({ label, aside, children, note }: { label: string; aside?: ReactNode; children: ReactNode; note: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-2 bg-lunar-900 p-4">
      <dt className="flex items-center justify-between gap-2 text-[0.65rem] uppercase tracking-[0.16em] text-electrum/75">
        <span className="truncate">{label}</span>
        {aside}
      </dt>
      <dd className="min-w-0">
        {children}
        <p className="mt-2 text-[0.7rem] text-electrum/65">{note}</p>
      </dd>
    </div>
  );
}

function Awaiting({ disconnected }: { disconnected: boolean }) {
  return <Chip tone="muted">{disconnected ? 'DISCONNECTED' : 'AWAITING'}</Chip>;
}

/** Live counters derived only from telemetry.frame rows received in this browser session. */
export function KpiStrip({ rows, disconnected }: { rows: readonly AuditRow[]; disconnected: boolean }) {
  const s = auditStats(rows);
  const recent = recentVerdicts(rows, RECENT);
  const recentRejected = recent.filter((v) => v === 'REJECTED').length;
  const last = s.latest;
  const lastFrame = last?.telemetry.frame ?? null;

  return (
    <section aria-label="Session counters" className="mt-6">
      <dl className="grid grid-cols-1 gap-px border border-electrum/15 bg-electrum/15 sm:grid-cols-2 2xl:grid-cols-4">
        <Cell label="Frames this session" note={`Client window, newest ${AUDIT_LIMIT} rows.`}>
          {s.total === 0 ? (
            <Awaiting disconnected={disconnected} />
          ) : (
            <p className="flex flex-wrap items-baseline gap-x-4 font-mono tabular">
              <span>
                <span className="text-2xl text-phosphor">{s.accepted}</span>
                <span className="ml-1 text-xs text-electrum/75">accepted</span>
              </span>
              <span>
                <span className="text-2xl text-phosphor">{s.rejected}</span>
                <span className="ml-1 text-xs text-electrum/75">rejected</span>
              </span>
            </p>
          )}
        </Cell>

        <Cell
          label={`Last ${RECENT} verdicts`}
          note={
            recent.length === 0
              ? 'Accepted cells are phosphor, rejected cells are filled gold.'
              : `${recent.length - recentRejected} accepted, ${recentRejected} rejected, oldest left.`
          }
        >
          {recent.length === 0 ? (
            <Awaiting disconnected={disconnected} />
          ) : (
            <ol aria-label={`Last ${recent.length} verdicts, oldest first`} className="flex h-6 gap-px">
              {recent.map((v, i) => (
                <li
                  key={i}
                  title={v}
                  className={`h-full flex-1 ${v === 'ACCEPTED' ? 'bg-phosphor/70' : 'bg-electrum'}`}
                >
                  <span className="sr-only">{v}</span>
                </li>
              ))}
            </ol>
          )}
        </Cell>

        <Cell
          label="Last frame"
          aside={last ? <Chip tone={last.telemetry.verdict === 'ACCEPTED' ? 'ok' : 'warn'}>{last.telemetry.verdict}</Chip> : null}
          note={last ? `${last.telemetry.reason} · ${last.telemetry.source.kind} · ${last.telemetry.received_at}` : 'No telemetry.frame event yet.'}
        >
          {last ? (
            <p className="font-mono tabular">
              <span className="text-2xl text-phosphor">{lastFrame ? `#${lastFrame.seq}` : 'N/A'}</span>
              <span className="ml-2 text-xs text-electrum/80">
                {lastFrame ? `${lastFrame.frame_type} ${commandLabel(lastFrame)}` : 'not decoded'}
              </span>
            </p>
          ) : (
            <Awaiting disconnected={disconnected} />
          )}
        </Cell>

        <Cell
          label="Tone deviation, last frame"
          aside={last?.anomaly ? <Chip tone="info">Tone anomaly</Chip> : null}
          note={`Frames above 50 Hz this session: ${s.anomalies}.`}
        >
          {last ? (
            <p className="font-mono tabular">
              <span className="text-2xl text-phosphor">{last.telemetry.source.frequency_deviation_hz}</span>
              <span className="ml-1 text-xs text-electrum/75">Hz</span>
            </p>
          ) : (
            <Awaiting disconnected={disconnected} />
          )}
        </Cell>
      </dl>
    </section>
  );
}
