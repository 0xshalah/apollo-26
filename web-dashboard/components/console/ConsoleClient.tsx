'use client';

import { useEffect, useReducer } from 'react';
import { AppHeader } from '@/components/AppHeader';
import { Chip } from '@/components/Panel';
import { AuditLedger } from '@/components/console/AuditLedger';
import { DskyInstrument, DskySheet } from '@/components/console/Dsky';
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

function connectionLabel(c: ConnectionState): { text: string; tone: 'ok' | 'warn' | 'muted' } {
  switch (c.kind) {
    case 'connected':
      return { text: 'CONNECTED', tone: 'ok' };
    case 'connecting':
      return { text: c.attempt === 0 ? 'CONNECTING' : `RECONNECTING (attempt ${c.attempt})`, tone: 'muted' };
    case 'disconnected':
      return { text: `DISCONNECTED · retry in ${(c.nextRetryMs / 1000).toFixed(1)} s`, tone: 'warn' };
    case 'unsupported':
      return { text: 'DISCONNECTED · WebSocket unavailable', tone: 'warn' };
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

  return (
    <>
      <AppHeader current="console">
        <span role="status" aria-live="polite" aria-label={`Daemon link: ${conn.text}`}>
          <Chip tone={conn.tone}>{conn.text}</Chip>
        </span>
      </AppHeader>
      <div className="mx-auto grid max-w-[110rem] grid-cols-1 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <main id="main" className="min-w-0 px-4 py-6 sm:px-6">
          <h1 className="font-display text-4xl sm:text-5xl">Mission console</h1>
          <p className="mt-2 max-w-prose text-sm text-electrum/75">
            Read-only view of the local daemon at <span className="font-mono">{WS_PATH}</span>. Every event is validated
            against the contract schemas before display; missing data is shown as UNMEASURED or DISCONNECTED.
          </p>
          {disconnected && state.connection.kind !== 'connecting' ? (
            <p role="alert" className="mt-4 border border-electrum bg-lunar-800 p-3 text-sm">
              DISCONNECTED from the daemon. Values shown are the last received and marked STALE. Open this page from the
              daemon (http://127.0.0.1) to connect.
            </p>
          ) : null}
          <div className="mt-6 grid grid-cols-1 gap-6 2xl:grid-cols-[minmax(0,1fr)_20rem]">
            <div className="min-w-0 space-y-6">
              <SpectrumPanel spectrum={state.spectrum} disconnected={disconnected} />
              <AuditLedger
                rows={state.audit}
                selectedId={state.selectedAuditEventId}
                onSelect={(id) => dispatch({ type: 'select', eventId: id })}
                connection={state.connection}
              />
            </div>
            <div className="grid min-w-0 grid-cols-1 content-start gap-6 md:grid-cols-2 2xl:grid-cols-1">
              <SystemStatusPanel system={state.system} disconnected={disconnected} />
              <TestSummaryPanel tests={state.tests} disconnected={disconnected} />
              <DiagnosticsPanel diagnostics={state.diagnostics} ignored={state.ignoredOutOfOrder} />
            </div>
          </div>
        </main>
        <aside aria-label="DSKY" className="hidden border-l border-electrum/15 bg-lunar-900 p-5 xl:block">
          <div className="sticky top-5">
            <h2 className="mb-3 font-display text-2xl">DSKY</h2>
            <DskyInstrument agc={state.agc} disconnected={disconnected} />
          </div>
        </aside>
      </div>
      <DskySheet agc={state.agc} disconnected={disconnected} />
    </>
  );
}
