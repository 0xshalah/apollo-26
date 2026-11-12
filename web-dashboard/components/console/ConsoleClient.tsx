'use client';

import { useEffect, useReducer } from 'react';
import { AppShell, type ShellSection } from '@/components/AppShell';
import { Chip } from '@/components/Panel';
import { AuditLedger } from '@/components/console/AuditLedger';
import { ConsoleHeader } from '@/components/console/ConsoleHeader';
import { DskyInstrument, DskySheet } from '@/components/console/Dsky';
import { KpiStrip } from '@/components/console/KpiStrip';
import { LinkSnapshotPanel } from '@/components/console/LinkSnapshotPanel';
import { SpectrumPanel } from '@/components/console/SpectrumPanel';
import { DiagnosticsPanel, SystemStatusPanel, TestSummaryPanel } from '@/components/console/StatusPanels';
import {
  backoffDelayMs,
  consoleReducer,
  initialConsoleState,
  socketUrl,
  type ConnectionState,
} from '@/lib/console-state';
import { parseConsoleMessage } from '@/lib/events';

/** Same-origin WebSocket path served by the daemon on 127.0.0.1. Overridable at build time. */
const WS_PATH = process.env.NEXT_PUBLIC_APOLLO26_WS_PATH || '/ws';

const SECTIONS: readonly ShellSection[] = [
  { id: 'spectrum', label: 'Acoustic link' },
  { id: 'system', label: 'System & Flight Watch' },
  { id: 'audit', label: 'Frame audit log' },
  { id: 'tests', label: 'Test evidence' },
  { id: 'diagnostics', label: 'Contract diagnostics' },
];

function connectionLabel(c: ConnectionState): { text: string; tone: 'ok' | 'bad' | 'muted' } {
  switch (c.kind) {
    case 'connected':
      return { text: 'CONNECTED', tone: 'ok' };
    case 'connecting':
      return { text: c.attempt === 0 ? 'CONNECTING' : `RECONNECTING (attempt ${c.attempt})`, tone: 'muted' };
    case 'disconnected':
      return { text: `DISCONNECTED · retry in ${(c.nextRetryMs / 1000).toFixed(1)} s`, tone: 'bad' };
    case 'unsupported':
      return { text: 'DISCONNECTED · WebSocket unavailable', tone: 'bad' };
  }
}

export function ConsoleClient() {
  const [state, dispatch] = useReducer(consoleReducer, initialConsoleState);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;
    let disposed = false;

    const scheduleReconnect = () => {
      if (disposed) return;
      attempt += 1;
      const delay = backoffDelayMs(attempt - 1, Math.random);
      dispatch({ type: 'disconnected', attempt, nextRetryMs: delay });
      timer = setTimeout(open, delay);
    };

    function open() {
      if (disposed) return;
      if (typeof WebSocket === 'undefined') {
        dispatch({ type: 'unsupported', message: 'WebSocket is not available in this browser.' });
        return;
      }
      dispatch({ type: 'connecting', attempt });
      let ws: WebSocket;
      try {
        ws = new WebSocket(socketUrl(window.location, WS_PATH));
      } catch {
        scheduleReconnect();
        return;
      }
      socket = ws;
      ws.onopen = () => {
        attempt = 0;
        dispatch({ type: 'connected', at: new Date().toISOString() });
      };
      ws.onmessage = (msg) => {
        const r = parseConsoleMessage(msg.data);
        if (r.ok) dispatch({ type: 'event', event: r.event });
        else dispatch({ type: 'diagnostic', diagnostic: r.diagnostic, at: new Date().toISOString() });
      };
      ws.onclose = () => {
        socket = null;
        scheduleReconnect();
      };
      ws.onerror = () => {
        /* onclose follows and handles reconnect */
      };
    }

    timer = setTimeout(open, 0);
    return () => {
      disposed = true;
      if (timer) clearTimeout(timer);
      if (socket) {
        socket.onclose = null;
        socket.close();
      }
    };
  }, []);

  const disconnected = state.connection.kind !== 'connected';
  const conn = connectionLabel(state.connection);
  const latest = state.audit.length > 0 ? state.audit[state.audit.length - 1] : null;

  return (
    <AppShell
      current="console"
      sections={SECTIONS}
      status={
        <span role="status" aria-live="polite" aria-label={`Daemon link: ${conn.text}`}>
          <Chip tone={conn.tone}>{conn.text}</Chip>
        </span>
      }
    >
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_21.75rem]">
        <main id="main" className="min-w-0">
          <ConsoleHeader state={state} />

          <KpiStrip rows={state.audit} disconnected={disconnected} />

          <div className="space-y-6 p-4 sm:p-6">
            {disconnected && state.connection.kind !== 'connecting' ? (
              <p role="alert" className="rounded-card border border-bad bg-bad-soft p-3 text-sm text-ink">
                DISCONNECTED from the daemon. Values shown are the last received and marked STALE. Open this page from the
                daemon (http://127.0.0.1) to connect.
              </p>
            ) : null}

            <div className="grid grid-cols-1 gap-6 min-[90rem]:grid-cols-[minmax(0,1.25fr)_minmax(18rem,0.75fr)]">
              <SpectrumPanel spectrum={state.spectrum} disconnected={disconnected} />
              <LinkSnapshotPanel latest={latest} disconnected={disconnected} />
            </div>

            <div className="grid grid-cols-1 items-start gap-6 min-[90rem]:grid-cols-[minmax(0,1fr)_18rem]">
              <AuditLedger
                rows={state.audit}
                selectedId={state.selectedAuditEventId}
                onSelect={(id) => dispatch({ type: 'select', eventId: id })}
                connection={state.connection}
              />
              <SystemStatusPanel system={state.system} disconnected={disconnected} />
            </div>

            <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
              <TestSummaryPanel tests={state.tests} disconnected={disconnected} />
              <DiagnosticsPanel diagnostics={state.diagnostics} ignored={state.ignoredOutOfOrder} />
            </div>
          </div>
        </main>
        <aside aria-label="DSKY" className="hidden border-l border-rule bg-paper-3 p-4 xl:block">
          <div className="sticky top-4">
            <div className="mb-4 flex items-center justify-between border-b border-rule pb-2">
              <h2 className="text-[0.9375rem] text-ink">DSKY Block II (1969)</h2>
              <span className="font-mono text-[0.65rem] text-muted">AGC SUBSET</span>
            </div>
            <DskyInstrument agc={state.agc} disconnected={disconnected} />
          </div>
        </aside>
      </div>
      <DskySheet agc={state.agc} disconnected={disconnected} />
    </AppShell>
  );
}
