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
  'group flex min-h-11 items-center gap-3 rounded-pill border border-transparent px-3 text-sm font-medium text-ink-2 transition-colors hover:border-rule hover:bg-paper-2 hover:text-ink';
const navKey = 'rounded-tag bg-paper-2 px-1.5 py-0.5 font-mono text-xs leading-none text-muted';

/**
 * Mockup sidebar (expanded rail): brand, route links, numbered "On this page" sections,
 * and a status card at the bottom from `lg` up; a compact top bar below that. The status
 * slot renders once so live regions are not duplicated.
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
    <div className="lg:grid lg:min-h-dvh lg:grid-cols-[15.25rem_minmax(0,1fr)]">
      <aside className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-rule bg-paper-3 px-4 py-2 lg:sticky lg:top-0 lg:h-dvh lg:flex-col lg:flex-nowrap lg:items-stretch lg:gap-0 lg:overflow-y-auto lg:border-b-0 lg:border-r lg:px-3 lg:py-4">
        <div className="lg:px-1 lg:pb-4">
          <Link href="/" className="inline-flex min-h-11 items-center gap-2 text-lg font-medium tracking-tight text-ink">
            <span aria-hidden className="font-mono text-accent">
              {'///'}
            </span>
            Apollo-26
          </Link>
        </div>
        <nav aria-label="Primary" className="flex flex-wrap gap-1 lg:grid lg:border-t lg:border-rule lg:pt-4">
          {ROUTES.map((r) => (
            <Link
              key={r.route}
              href={r.href}
              aria-current={current === r.route ? 'page' : undefined}
              className={`${navItem} aria-[current=page]:border-rule-2 aria-[current=page]:bg-paper-2 aria-[current=page]:text-ink aria-[current=page]:shadow-[inset_3px_0_0_var(--color-accent)]`}
            >
              <span className="flex-1">{r.label}</span>
              <span aria-hidden className={`${navKey} hidden group-aria-[current=page]:text-accent lg:inline`}>
                {r.key}
              </span>
            </Link>
          ))}
        </nav>

        {sections.length > 0 ? (
          <nav aria-label="On this page" className="hidden pt-5 lg:block">
            <p className="px-3 pb-2 text-xs font-medium text-muted">On this page</p>
            <ol className="grid gap-1">
              {sections.map((s, i) => (
                <li key={s.id}>
                  <a href={`#${s.id}`} className={navItem}>
                    <span className="flex-1 truncate">{s.label}</span>
                    <span aria-hidden className={`${navKey} tabular`}>
                      {String(i + 1).padStart(2, '0')}
                    </span>
                  </a>
                </li>
              ))}
            </ol>
          </nav>
        ) : null}

        {status ? (
          <div className="ml-auto flex items-center lg:ml-0 lg:mt-auto lg:block lg:border-t lg:border-rule lg:pt-4">
            <div className="lg:rounded-pill lg:border lg:border-rule lg:bg-paper-2 lg:px-3 lg:py-2">
              <p className="hidden pb-1.5 text-xs text-ink-2 lg:block">Daemon link</p>
              {status}
            </div>
          </div>
        ) : null}
      </aside>
      <div className="min-w-0">{children}</div>
    </div>
  );
}
