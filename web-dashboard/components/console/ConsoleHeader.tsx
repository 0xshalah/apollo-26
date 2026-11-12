import { Chip } from '@/components/Panel';
import { AUDIT_LIMIT, type ConsoleState, type PanelValue } from '@/lib/console-state';
import type { AgcStateData, SystemStatusData } from '@/lib/events';
import { pad2 } from '@/lib/format';

function value<T>(panel: PanelValue<T>): T | null {
  return panel.kind === 'loading' ? null : panel.value;
}

function freshness(panel: PanelValue<unknown>): 'LIVE' | 'STALE' | 'AWAITING' {
  if (panel.kind === 'loading') return 'AWAITING';
  return panel.kind === 'stale' ? 'STALE' : 'LIVE';
}

function AgcValue({ agc }: { agc: PanelValue<AgcStateData> }) {
  const current = value(agc);
  return current ? (
    <span className="font-mono text-ink tabular">P{pad2(current.program)} · V{pad2(current.verb)} N{pad2(current.noun)}</span>
  ) : (
    <span className="text-muted">Awaiting</span>
  );
}

function FlightWatchValue({ system }: { system: PanelValue<SystemStatusData> }) {
  const current = value(system);
  if (!current) return <span className="text-muted">Awaiting</span>;
  const bad = current.flight_watch === 'HALTED';
  return <span className={bad ? 'text-bad' : 'text-ink'}>{current.flight_watch}</span>;
}

/** Dense, read-only command bar derived from the current console reducer state. */
export function ConsoleHeader({ state }: { state: ConsoleState }) {
  const latest = state.audit.length > 0 ? state.audit[state.audit.length - 1] : null;
  const frame = latest?.telemetry.frame ?? null;
  const statusFreshness = freshness(state.system);
  const stale = state.connection.kind !== 'connected';

  return (
    <header className="sticky top-0 z-30 border-b border-rule bg-paper-3/95 backdrop-blur">
      <div className="grid gap-3 px-4 py-3 sm:px-6">
        <div className="flex min-w-0 items-center justify-between gap-3">
          <div>
            <p className="font-mono text-[0.65rem] text-accent">ACOUSTIC BRIDGE / READ ONLY</p>
            <h1 className="mt-0.5 text-[1.35rem] text-ink">Mission console</h1>
          </div>
          {stale && state.connection.kind !== 'connecting' ? <Chip tone="bad">link stale</Chip> : null}
        </div>
        <dl className="grid w-full grid-cols-2 gap-px overflow-hidden rounded-pill border border-rule bg-rule sm:grid-cols-4">
          <div className="min-w-0 bg-paper px-3 py-2">
            <dt className="text-[0.65rem] text-muted">Frame window</dt>
            <dd className="mt-0.5 font-mono text-xs text-ink tabular">{state.audit.length} / {AUDIT_LIMIT}</dd>
          </div>
          <div className="min-w-0 bg-paper px-3 py-2">
            <dt className="text-[0.65rem] text-muted">Latest sequence</dt>
            <dd className="mt-0.5 font-mono text-xs text-ink tabular">{frame ? frame.seq : '—'}</dd>
          </div>
          <div className="min-w-0 bg-paper px-3 py-2">
            <dt className="text-[0.65rem] text-muted">AGC display</dt>
            <dd className="mt-0.5 truncate text-xs"><AgcValue agc={state.agc} /></dd>
          </div>
          <div className="min-w-0 bg-paper px-3 py-2">
            <dt className="flex items-center justify-between gap-2 text-[0.65rem] text-muted">
              <span>Flight Watch</span>
              {statusFreshness !== 'LIVE' ? <Chip tone={statusFreshness === 'STALE' ? 'warn' : 'muted'}>{statusFreshness}</Chip> : null}
            </dt>
            <dd className="mt-0.5 text-xs"><FlightWatchValue system={state.system} /></dd>
          </div>
        </dl>
      </div>
    </header>
  );
}
