import { Chip, Panel } from '@/components/Panel';
import type { PanelValue, TimedDiagnostic } from '@/lib/console-state';
import type { SystemStatusData, TestSummaryData } from '@/lib/events';

function Freshness({ p, disconnected }: { p: PanelValue<unknown>; disconnected: boolean }) {
  if (p.kind === 'loading') return <Chip tone={disconnected ? 'bad' : 'muted'}>{disconnected ? 'DISCONNECTED' : 'AWAITING'}</Chip>;
  if (p.kind === 'stale') return <Chip tone="warn">STALE</Chip>;
  return <Chip tone="ok">LIVE</Chip>;
}

const HEALTHY = new Set(['READY', 'STANDBY', 'WAITING', 'PROCESSING']);
const BAD = new Set(['STOPPED', 'ERROR', 'HALTED']);

export function SystemStatusPanel({ system, disconnected }: { system: PanelValue<SystemStatusData>; disconnected: boolean }) {
  const v = system.kind === 'loading' ? null : system.value;
  const rows: Array<{ label: string; value: string | null }> = [
    { label: 'Daemon', value: v?.daemon ?? null },
    { label: 'Audio input', value: v?.audio ?? null },
    { label: 'AGC emulator', value: v?.agc ?? null },
    { label: 'Kiro Flight Watch', value: v?.flight_watch ?? null },
  ];
  return (
    <Panel id="system" title="System & Flight Watch" aside={<Freshness p={system} disconnected={disconnected} />}>
      <dl className="overflow-hidden rounded-pill border border-rule">
        {rows.map((r) => (
          <div key={r.label} className="flex items-center justify-between gap-3 border-b border-rule bg-paper-3 px-3 py-2.5 last:border-b-0">
            <dt className="text-sm text-ink-2">{r.label}</dt>
            <dd>
              {r.value === null ? (
                <Chip tone={disconnected ? 'bad' : 'muted'}>{disconnected ? 'DISCONNECTED' : 'UNMEASURED'}</Chip>
              ) : (
                <Chip tone={HEALTHY.has(r.value) ? 'ok' : BAD.has(r.value) ? 'bad' : 'warn'}>{r.value}</Chip>
              )}
            </dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 text-xs text-muted">
        Flight Watch PROCESSING covers inspection, planning, authorization wait, execution, and verification; the event
        contract does not publish those substates.
      </p>
      {system.kind !== 'loading' ? (
        <p className="mt-1 font-mono text-xs text-muted">
          event #{system.eventId} · {system.timestamp}
        </p>
      ) : null}
    </Panel>
  );
}

export function TestSummaryPanel({ tests, disconnected }: { tests: PanelValue<TestSummaryData>; disconnected: boolean }) {
  return (
    <Panel id="tests" title="Test evidence" aside={<Freshness p={tests} disconnected={disconnected} />}>
      {tests.kind === 'loading' ? (
        <p className="text-sm text-muted">
          <Chip tone="muted">UNMEASURED</Chip>
          <span className="ml-2">No test.summary event received. The console never runs tests itself.</span>
        </p>
      ) : (
        <>
          <dl className="grid grid-cols-3 gap-px overflow-hidden rounded-pill border border-rule bg-rule text-center">
            {(
              [
                ['Passed', tests.value.passed, 'text-ok'],
                ['Failed', tests.value.failed, tests.value.failed > 0 ? 'text-bad' : 'text-ink'],
                ['Skipped', tests.value.skipped, 'text-ink'],
              ] as const
            ).map(([label, n, tone]) => (
              <div key={label} className="bg-paper-3 py-3">
                <dt className="text-xs text-muted">{label}</dt>
                <dd className={`font-mono text-[1.35rem] font-medium tabular ${tone}`}>{n}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-3 text-xs">
            {tests.value.failed > 0 ? (
              <Chip tone="bad">{tests.value.failed} failed</Chip>
            ) : (
              <Chip tone="ok">No failures reported</Chip>
            )}
          </p>
          <dl className="mt-3 space-y-1 font-mono text-xs text-ink-2">
            <div>
              <dt className="inline text-muted">profile </dt>
              <dd className="inline">{tests.value.profile}</dd>
            </div>
            <div>
              <dt className="inline text-muted">report </dt>
              <dd className="inline break-all text-cool">{tests.value.report_path}</dd>
            </div>
            <div>
              <dt className="inline text-muted">event </dt>
              <dd className="inline">
                #{tests.eventId} · {tests.timestamp}
              </dd>
            </div>
          </dl>
        </>
      )}
    </Panel>
  );
}

export function DiagnosticsPanel({ diagnostics, ignored }: { diagnostics: readonly TimedDiagnostic[]; ignored: number }) {
  return (
    <Panel id="diagnostics" title="Contract diagnostics">
      {diagnostics.length === 0 ? (
        <p className="text-sm text-muted">No invalid messages received.</p>
      ) : (
        <ol className="max-h-48 space-y-1 overflow-auto rounded-pill border border-rule bg-paper-3 p-3 font-mono text-xs text-ink-2">
          {[...diagnostics].reverse().map((d, i) => (
            <li key={`${d.at}-${i}`}>
              {d.at} · <span className="text-bad">{d.category}</span> · {d.details.join('; ')}
            </li>
          ))}
        </ol>
      )}
      <p className="mt-3 text-xs text-muted">
        Invalid messages are dropped without changing any panel. Out-of-order events ignored: {ignored}.
      </p>
    </Panel>
  );
}
