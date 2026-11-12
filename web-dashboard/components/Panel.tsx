import type { ReactNode } from 'react';

/** Hairline instrument panel. `ticks` adds corner ticks; reserve for primary instruments. */
export function Panel({
  title,
  id,
  ticks = false,
  aside,
  children,
  className = '',
}: {
  title: string;
  id: string;
  ticks?: boolean;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      aria-labelledby={`${id}-title`}
      className={`min-w-0 border border-electrum/15 bg-lunar-900 ${ticks ? 'ticks' : ''} ${className}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-electrum/15 px-4 py-2">
        <h2 id={`${id}-title`} className="text-xs font-semibold uppercase tracking-[0.18em] text-electrum/80">
          {title}
        </h2>
        {aside}
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}

export type Tone = 'ok' | 'warn' | 'muted' | 'info';

/** Text-labelled status chip; color is never the only cue. */
export function Chip({ tone, children }: { tone: Tone; children: ReactNode }) {
  const styles: Record<Tone, string> = {
    ok: 'border-phosphor/60 text-phosphor',
    warn: 'border-electrum bg-electrum text-void',
    muted: 'border-electrum/25 text-electrum/70',
    info: 'border-electrum/50 text-electrum',
  };
  return (
    <span className={`inline-flex items-center border px-2 py-0.5 font-mono text-[0.7rem] uppercase tracking-wider ${styles[tone]}`}>
      {children}
    </span>
  );
}
