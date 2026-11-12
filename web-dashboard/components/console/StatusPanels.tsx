import { Chip, Panel } from '@/components/Panel';
import type { PanelValue, TimedDiagnostic } from '@/lib/console-state';
import type { SystemStatusData, TestSummaryData } from '@/lib/events';

function Freshness({ p, disconnected }: { p: PanelValue<unknown>; disconnected: boolean }) {
  if (p.kind === 'loading') return <Chip tone="muted">{disconnected ? 'DISCONNECTED' : 'AWAITING'}</Chip>;
  if (p.kind === 'stale') return <Chip tone="warn">STALE</Chip>;
  return <Chip tone="ok">LIVE</Chip>;
}

const HEALTHY = new Set(['READY', 'STANDBY', 'WAITING', 'PROCESSING']);

export function SystemStatusPanel({ system, disconnected }: { system: PanelValue<SystemStatusData>; disconnected: boolean }) {
  const v = system.kind === 'loading' ? null : system.value;
  const rows: Array<{ label: string; value: string | null }> = [
    { label: 'Daemon', value: v?.daemon ?? null },
    { label: 'Audio input', value: v?.audio ?? null },
    { label: 'AGC emulator', value: v?.agc ?? null },
    { label: 'Kiro Flight Watch', value: v?.flight_watch ?? null },
  ];
  return (
    <Panel id="system" title="System status" aside={<Freshness p={system} disconnected={disconnected} />}>
      <dl className="grid gap-px bg-electrum/10">
        {rows.map((r) => (
          <div key={r.label} className="flex items-center justify-between gap-3 bg-lunar-900 py-2">
            <dt className="text-sm text-electrum/80">{r.label}</dt>
            <dd>
              {r.value === null ? (
                <Chip tone="muted">{disconnected ? 'DISCONNECTED' : 'UNMEASURED'}</Chip>
              ) : (
                <Chip tone={HEALTHY.has(r.value) ? 'ok' : 'warn'}>{r.value}</Chip>
              )}
            </dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 text-[0.7rem] text-electrum/65">
        Flight Watch PROCESSING covers inspection, planning, authorization wait, execution, and verification; the event
        contract does not publish those substates.
      </p>
      {system.kind !== 'loading' ? (
        <p className="mt-1 font-mono text-[0.7rem] text-electrum/60">
          event #{system.eventId} · {system.timestamp}
        </p>
      ) : null}
    </Panel>
  );
}

export function TestSummaryPanel({ tests, disconnected }: { tests: PanelValue<TestSummaryData>; disconnected: boolean }) {
  return (
    <Panel id="tests" title="Latest test summary" aside={<Freshness p={tests} disconnected={disconnected} />}>
      {tests.kind === 'loading' ? (
        <p className="text-sm">
          <Chip tone="muted">UNMEASURED</Chip>
          <span className="ml-2 text-electrum/70">No test.summary event received. The console never runs tests itself.</span>
        </p>
      ) : (
        <>
          <dl className="grid grid-cols-3 gap-px bg-electrum/10 text-center">
            {(
              [
                ['Passed', tests.value.passed],
                ['Failed', tests.value.failed],
                ['Skipped', tests.value.skipped],
              ] as const
            ).map(([label, n]) => (
              <div key={label} className={`py-2 ${label === 'Failed' && n > 0 ? 'bg-electrum text-void' : 'bg-lunar-900'}`}>
                <dt className="text-[0.65rem] uppercase tracking-[0.16em]">{label}</dt>
                <dd className="font-mono text-2xl tabular">{n}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-2 text-xs">
            {tests.value.failed > 0 ? (
              <Chip tone="warn">{tests.value.failed} FAILED</Chip>
            ) : (
              <Chip tone="ok">No failures reported</Chip>
            )}
          </p>
          <dl className="mt-2 space-y-1 font-mono text-xs text-electrum/80">
            <div>
              <dt className="inline text-electrum/60">profile </dt>
              <dd className="inline">{tests.value.profile}</dd>
            </div>
            <div>
              <dt className="inline text-electrum/60">report </dt>
              <dd className="inline break-all">{tests.value.report_path}</dd>
            </div>
            <div>
              <dt className="inline text-electrum/60">event </dt>
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
        <p className="text-xs text-electrum/70">No invalid messages received.</p>
      ) : (
        <ol className="max-h-48 space-y-1 overflow-auto font-mono text-[0.7rem] text-electrum/80">
          {[...diagnostics].reverse().map((d, i) => (
            <li key={`${d.at}-${i}`}>
              {d.at} · {d.category} · {d.details.join('; ')}
            </li>
          ))}
        </ol>
      )}
      <p className="mt-2 text-[0.7rem] text-electrum/60">
        Invalid messages are dropped without changing any panel. Out-of-order events ignored: {ignored}.
      </p>
    </Panel>
  );
}
