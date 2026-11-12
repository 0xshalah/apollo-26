import Link from 'next/link';
import { AppShell } from '@/components/AppShell';

const CARDS = [
  {
    href: '/ground/',
    key: 'TX',
    title: 'Ground station',
    body: 'Compose, sign, inspect, and transmit COMMAND and AUTH frames.',
  },
  {
    href: '/console/',
    key: 'RX',
    title: 'Mission console',
    body: 'Read-only DSKY, spectrum, frame audit, and status from the local daemon.',
  },
];

export default function HomePage() {
  return (
    <AppShell current="home">
      <main id="main" className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
        <h1 className="text-[2.5rem] text-ink sm:text-[3.25rem]">Apollo-26</h1>
        <p className="mt-4 max-w-prose text-muted">
          An emergency command path without an IP interface: the ground station transmits authenticated 300-baud
          Bell-202 frames as sound, the local daemon validates them, and a Kiro Flight Watch session plans DSKY input
          through the MCP safety gate for an AGC-faithful subset emulator (P00 and simplified P40).
        </p>
        <ul className="mt-10 grid gap-4 sm:grid-cols-2">
          {CARDS.map((c) => (
            <li key={c.href}>
              <Link
                href={c.href}
                className="block min-h-11 rounded-card border border-rule-2 bg-paper-2 p-6 transition-colors hover:border-ink-2 hover:bg-paper-3"
              >
                <span className="flex items-center justify-between gap-3">
                  <span className="text-[1.35rem] font-medium tracking-tight text-ink">{c.title}</span>
                  <span aria-hidden className="rounded-tag bg-paper-3 px-1.5 py-0.5 font-mono text-xs text-accent">
                    {c.key}
                  </span>
                </span>
                <span className="mt-2 block text-sm text-muted">{c.body}</span>
              </Link>
            </li>
          ))}
        </ul>
        <p className="mt-8 text-xs text-muted">
          The emulator does not run Luminary or Colossus flight software. Kiro uses a cloud LLM; only the
          daemon–MCP–AGC command path is local.
        </p>
      </main>
    </AppShell>
  );
}
