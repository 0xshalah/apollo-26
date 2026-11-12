import Link from 'next/link';
import type { ReactNode } from 'react';

export type Route = 'home' | 'ground' | 'console';

export interface ShellSection {
  /** Element id of the panel to jump to (Panel `id`). */
  id: string;
  label: string;
}

const ROUTES: Array<{ route: Route; href: string; label: string; key: string }> = [
  { route: 'ground', href: '/ground/', label: 'Ground station', key: 'TX' },
  { route: 'console', href: '/console/', label: 'Mission console', key: 'RX' },
];

const navItem =
  'flex min-h-11 items-center gap-3 border border-transparent px-3 text-sm text-electrum/80 hover:border-electrum/30 hover:text-electrum';

/**
 * Instrument-rail layout: a left sidebar (routes, numbered sections on this page,
 * and a status slot) from `lg` up; a compact top bar below that. The status slot
 * is rendered once so live regions are not duplicated.
 */
export function AppShell({
  current,
  sections = [],
  status,
  children,
}: {
  current: Route;
  sections?: readonly ShellSection[];
  status?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="lg:grid lg:min-h-dvh lg:grid-cols-[15rem_minmax(0,1fr)]">
      <aside className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-electrum/15 bg-void px-4 py-2 lg:sticky lg:top-0 lg:h-dvh lg:flex-col lg:flex-nowrap lg:items-stretch lg:gap-0 lg:overflow-y-auto lg:border-b-0 lg:border-r lg:px-0 lg:py-0">
        <div className="lg:px-4 lg:pt-5">
          <Link href="/" className="inline-flex min-h-11 items-center font-display text-2xl tracking-wide">
            Apollo-26
          </Link>
        </div>
        <nav aria-label="Primary" className="flex flex-wrap gap-1 lg:mt-4 lg:grid lg:px-4 lg:pb-4">
          {ROUTES.map((r) => (
            <Link
              key={r.route}
              href={r.href}
              aria-current={current === r.route ? 'page' : undefined}
              className={`${navItem} uppercase tracking-[0.12em] aria-[current=page]:border-electrum/50 aria-[current=page]:bg-lunar-900 aria-[current=page]:text-electrum`}
            >
              <span className="flex-1">{r.label}</span>
              <span aria-hidden className="hidden font-mono text-[0.65rem] text-electrum/60 lg:inline">
                {r.key}
              </span>
            </Link>
          ))}
        </nav>

        {sections.length > 0 ? (
          <nav aria-label="On this page" className="hidden border-t border-electrum/15 px-4 py-4 lg:block">
            <p className="px-3 pb-2 text-[0.65rem] uppercase tracking-[0.18em] text-electrum/60">On this page</p>
            <ol className="grid gap-1">
              {sections.map((s, i) => (
                <li key={s.id}>
                  <a href={`#${s.id}`} className={navItem}>
                    <span className="flex-1">{s.label}</span>
                    <span aria-hidden className="font-mono text-[0.65rem] text-electrum/60 tabular">
                      {String(i + 1).padStart(2, '0')}
                    </span>
                  </a>
                </li>
              ))}
            </ol>
          </nav>
        ) : null}

        {status ? (
          <div className="ml-auto flex items-center lg:ml-0 lg:mt-auto lg:block lg:border-t lg:border-electrum/15 lg:px-4 lg:py-4">
            <p className="hidden pb-2 text-[0.65rem] uppercase tracking-[0.18em] text-electrum/60 lg:block">Daemon link</p>
            {status}
          </div>
        ) : null}
      </aside>
      <div className="min-w-0">{children}</div>
    </div>
  );
}
