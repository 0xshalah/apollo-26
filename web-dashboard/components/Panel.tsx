import type { ReactNode } from 'react';

/** Rounded panel card (mockup .panel-box): title row with a hairline, then content. */
export function Panel({
  title,
  id,
  aside,
  children,
  className = '',
}: {
  title: string;
  id: string;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      id={id}
      aria-labelledby={`${id}-title`}
      className={`min-w-0 scroll-mt-6 rounded-card border border-rule-2 bg-paper-2 ${className}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-rule px-4 py-3">
        <h2 id={`${id}-title`} className="text-[0.9375rem] text-ink">
          {title}
        </h2>
        {aside}
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}

export type Tone = 'ok' | 'warn' | 'bad' | 'muted' | 'info';

/** Text-labelled status pill (mockup .pill); color is never the only cue. */
export function Chip({ tone, children }: { tone: Tone; children: ReactNode }) {
  const styles: Record<Tone, string> = {
    ok: 'bg-ok-soft text-ok',
    warn: 'bg-accent-soft text-accent',
    bad: 'bg-bad-soft text-bad',
    muted: 'bg-paper-3 text-muted',
    info: 'bg-cool-soft text-cool',
  };
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-tag px-2 py-0.5 text-xs font-medium ${styles[tone]}`}>
      {children}
    </span>
  );
}
