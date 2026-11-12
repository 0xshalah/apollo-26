import Link from 'next/link';
import type { ReactNode } from 'react';

type Route = 'home' | 'ground' | 'console';

const LINKS: Array<{ route: Route; href: string; label: string }> = [
  { route: 'ground', href: '/ground/', label: 'Ground station' },
  { route: 'console', href: '/console/', label: 'Mission console' },
];

export function AppHeader({ current, children }: { current: Route; children?: ReactNode }) {
  return (
    <header className="border-b border-electrum/15 bg-void">
      <div className="mx-auto flex max-w-[110rem] flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
        <Link href="/" className="inline-flex min-h-11 items-center font-display text-2xl tracking-wide">
          Apollo-26
        </Link>
        <nav aria-label="Primary" className="flex flex-wrap gap-1">
          {LINKS.map((l) => (
            <Link
              key={l.route}
              href={l.href}
              aria-current={current === l.route ? 'page' : undefined}
              className="inline-flex min-h-11 items-center border border-transparent px-3 text-sm uppercase tracking-[0.14em] text-electrum/80 hover:border-electrum/30 hover:text-electrum aria-[current=page]:border-electrum/40 aria-[current=page]:text-electrum"
            >
              {l.label}
            </Link>
          ))}
        </nav>
        {children ? <div className="ml-auto flex items-center gap-3">{children}</div> : null}
      </div>
    </header>
  );
}
