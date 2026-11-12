'use client';

import { useEffect, useRef, useState } from 'react';
import { Chip } from '@/components/Panel';
import type { PanelValue } from '@/lib/console-state';
import type { AgcStateData } from '@/lib/events';
import { pad2, signed5 } from '@/lib/format';

const LAMPS: Array<{ key: keyof AgcStateData['lamps']; label: string }> = [
  { key: 'comp_acty', label: 'COMP ACTY' },
  { key: 'uplink_acty', label: 'UPLINK ACTY' },
  { key: 'key_rel', label: 'KEY REL' },
  { key: 'opr_err', label: 'OPR ERR' },
];

function freshness(p: PanelValue<AgcStateData>, disconnected: boolean) {
  if (p.kind === 'loading') return <Chip tone={disconnected ? 'bad' : 'muted'}>{disconnected ? 'DISCONNECTED' : 'AWAITING'}</Chip>;
  if (p.kind === 'stale') return <Chip tone="warn">STALE</Chip>;
  return <Chip tone="ok">LIVE</Chip>;
}

/** Read-only projection of the daemon-owned AGC/DSKY state (mockup DSKY bezel). No keypad, no actuation. */
export function DskyInstrument({ agc, disconnected }: { agc: PanelValue<AgcStateData>; disconnected: boolean }) {
  const v = agc.kind === 'loading' ? null : agc.value;
  const dim = agc.kind === 'stale' ? 'opacity-60' : '';
  const seg = (label: string, value: string) => (
    <div className="grid gap-0.5 bg-paper px-3 py-2">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className={`font-mono text-[1.65rem] font-medium leading-tight text-ok tabular ${dim}`}>{value}</dd>
    </div>
  );
  const reg = (label: string, value: string) => (
    <div className="flex items-baseline justify-between gap-2 bg-paper px-3 py-2.5">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className={`font-mono text-[1.125rem] font-medium text-ok tabular ${dim}`}>{value}</dd>
    </div>
  );
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-muted">Read-only · daemon AGC state</p>
        {freshness(agc, disconnected)}
      </div>
      <div className="overflow-hidden rounded-card border border-rule-2 bg-rule-2">
        <dl className="grid grid-cols-3 gap-px bg-rule">
          {seg('Prog', v ? pad2(v.program) : '—')}
          {seg('Verb', v ? pad2(v.verb) : '—')}
          {seg('Noun', v ? pad2(v.noun) : '—')}
        </dl>
        <dl className="mt-px grid gap-px bg-rule">
          {reg('R1 azimuth', v ? signed5(v.r1) : '—')}
          {reg('R2 elevation', v ? signed5(v.r2) : '—')}
          {reg('R3 delta-v', v ? signed5(v.r3) : '—')}
        </dl>
      </div>
      <ul className="grid grid-cols-2 gap-1.5" aria-label="Lamps">
        {LAMPS.map((l) => {
          const on = v ? v.lamps[l.key] : null;
          const warnLamp = l.key === 'opr_err' || l.key === 'key_rel';
          return (
            <li
              key={l.key}
              className={`flex min-h-9 items-center justify-between gap-2 rounded-pill border px-3 text-xs font-medium ${
                on
                  ? warnLamp
                    ? 'border-bad bg-bad-soft text-bad'
                    : 'border-cool bg-cool-soft text-cool'
                  : 'border-rule bg-paper-2 text-muted'
              }`}
            >
              <span>{l.label}</span>
              <span className="font-mono">{on === null ? '—' : on ? 'ON' : 'OFF'}</span>
            </li>
          );
        })}
      </ul>
      <div className="rounded-card border border-rule bg-paper-2 p-3">
        {agc.kind === 'loading' ? (
          <p className="text-xs text-muted">Awaiting AGC state from the daemon. No values are shown until one arrives.</p>
        ) : (
          <p className="font-mono text-xs text-cool">
            event #{agc.eventId} · {agc.timestamp}
          </p>
        )}
        <p className="mt-2 text-xs text-muted">
          AGC-faithful subset emulator: P00 and simplified P40; V25, V34, V37. Not Luminary or Colossus. Keys are pressed only by
          the daemon after the MCP safety gate; this console has no keypad.
        </p>
      </div>
    </div>
  );
}

/** Compact bar + modal sheet for viewports below 80rem. Native <dialog> provides focus containment and Escape. */
export function DskySheet({ agc, disconnected }: { agc: PanelValue<AgcStateData>; disconnected: boolean }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const openerRef = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const v = agc.kind === 'loading' ? null : agc.value;

  useEffect(() => {
    const d = dialogRef.current;
    if (!d) return;
    if (open && !d.open) {
      d.showModal();
      document.body.style.overflow = 'hidden';
    }
    if (!open && d.open) d.close();
    return () => {
      document.body.style.overflow = '';
    };
  }, [open]);

  return (
    <div className="xl:hidden">
      <div className="sticky bottom-0 z-30 flex flex-wrap items-center gap-2 border-t border-rule-2 bg-paper-3/95 px-4 py-2 backdrop-blur">
        <span className="font-mono text-sm text-ok tabular">
          {v ? `P${pad2(v.program)} · V${pad2(v.verb)} N${pad2(v.noun)}` : 'DSKY —'}
        </span>
        {agc.kind === 'stale' ? <Chip tone="warn">STALE</Chip> : null}
        <button
          ref={openerRef}
          type="button"
          onClick={() => setOpen(true)}
          aria-haspopup="dialog"
          className="btn ml-auto"
        >
          Open DSKY
        </button>
      </div>
      <dialog
        ref={dialogRef}
        aria-labelledby="dsky-sheet-title"
        onClose={() => {
          setOpen(false);
          document.body.style.overflow = '';
          openerRef.current?.focus();
        }}
        className="dsky-sheet m-0 mt-auto max-h-[85dvh] w-full max-w-none overflow-y-auto rounded-t-card border-t border-rule-2 bg-paper-3 p-4 text-ink md:ml-auto md:mt-0 md:h-dvh md:max-h-none md:w-[24rem] md:rounded-none md:border-l md:border-t-0"
      >
        <div className="mb-4 flex items-center justify-between border-b border-rule pb-2">
          <h2 id="dsky-sheet-title" className="text-[0.9375rem] text-ink">
            DSKY Block II (1969)
          </h2>
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="btn"
          >
            Close
          </button>
        </div>
        <DskyInstrument agc={agc} disconnected={disconnected} />
      </dialog>
    </div>
  );
}
