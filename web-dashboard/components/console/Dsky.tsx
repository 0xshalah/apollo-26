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
  if (p.kind === 'loading') return <Chip tone="muted">{disconnected ? 'DISCONNECTED' : 'AWAITING'}</Chip>;
  if (p.kind === 'stale') return <Chip tone="warn">STALE</Chip>;
  return <Chip tone="ok">LIVE</Chip>;
}

/** Read-only projection of the daemon-owned AGC/DSKY state. No keypad, no actuation. */
export function DskyInstrument({ agc, disconnected }: { agc: PanelValue<AgcStateData>; disconnected: boolean }) {
  const v = agc.kind === 'loading' ? null : agc.value;
  const dim = agc.kind === 'stale' ? 'opacity-70' : '';
  const seg = (label: string, value: string) => (
    <div className="bg-lunar-900 px-3 py-2">
      <dt className="text-[0.65rem] uppercase tracking-[0.18em] text-electrum/70">{label}</dt>
      <dd className={`font-mono text-3xl leading-tight text-phosphor tabular ${dim}`}>{value}</dd>
    </div>
  );
  const reg = (label: string, value: string) => (
    <div className="flex items-baseline justify-between gap-2 bg-lunar-900 px-3 py-2">
      <dt className="text-xs text-electrum/70">{label}</dt>
      <dd className={`font-mono text-2xl text-phosphor tabular ${dim}`}>{value}</dd>
    </div>
  );
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs uppercase tracking-[0.16em] text-electrum/75">DSKY · read-only</p>
        {freshness(agc, disconnected)}
      </div>
      <div className="ticks border border-electrum/25 bg-electrum/15">
        <dl className="grid grid-cols-3 gap-px">
          {seg('Prog', v ? pad2(v.program) : '—')}
          {seg('Verb', v ? pad2(v.verb) : '—')}
          {seg('Noun', v ? pad2(v.noun) : '—')}
        </dl>
        <dl className="mt-px grid gap-px">
          {reg('R1', v ? signed5(v.r1) : '—')}
          {reg('R2', v ? signed5(v.r2) : '—')}
          {reg('R3', v ? signed5(v.r3) : '—')}
        </dl>
        <ul className="mt-px grid grid-cols-2 gap-px" aria-label="Lamps">
          {LAMPS.map((l) => {
            const on = v ? v.lamps[l.key] : null;
            return (
              <li
                key={l.key}
                className={`flex items-center justify-between gap-2 px-3 py-2 text-xs font-semibold tracking-wider ${
                  on ? 'bg-electrum text-void' : 'bg-lunar-900 text-electrum/70'
                }`}
              >
                <span>{l.label}</span>
                <span className="font-mono">{on === null ? '—' : on ? 'ON' : 'OFF'}</span>
              </li>
            );
          })}
        </ul>
      </div>
      {agc.kind === 'loading' ? (
        <p className="text-xs text-electrum/70">Awaiting AGC state from the daemon. No values are shown until one arrives.</p>
      ) : (
        <p className="font-mono text-[0.7rem] text-electrum/60">
          event #{agc.eventId} · {agc.timestamp}
        </p>
      )}
      <p className="text-[0.7rem] text-electrum/60">
        AGC-faithful subset emulator: P00 and simplified P40; V25, V34, V37. Not Luminary or Colossus.
      </p>
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
      <div className="sticky bottom-0 z-30 flex flex-wrap items-center gap-2 border-t border-electrum/40 bg-void/95 px-4 py-2">
        <span className="font-mono text-sm text-phosphor tabular">
          {v ? `P${pad2(v.program)} · V${pad2(v.verb)} N${pad2(v.noun)}` : 'DSKY —'}
        </span>
        {agc.kind === 'stale' ? <Chip tone="warn">STALE</Chip> : null}
        <button
          ref={openerRef}
          type="button"
          onClick={() => setOpen(true)}
          aria-haspopup="dialog"
          className="ml-auto inline-flex min-h-11 items-center border border-electrum/50 px-4 text-sm font-semibold uppercase tracking-[0.12em] hover:bg-lunar-800"
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
        className="dsky-sheet m-0 mt-auto max-h-[85dvh] w-full max-w-none overflow-y-auto border-t border-electrum/40 bg-lunar-900 p-4 text-electrum md:ml-auto md:mt-0 md:h-dvh md:max-h-none md:w-[24rem] md:border-l md:border-t-0"
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 id="dsky-sheet-title" className="font-display text-2xl">
            DSKY
          </h2>
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="inline-flex min-h-11 min-w-11 items-center justify-center border border-electrum/40 px-3 text-sm uppercase tracking-wider"
          >
            Close
          </button>
        </div>
        <DskyInstrument agc={agc} disconnected={disconnected} />
      </dialog>
    </div>
  );
}
