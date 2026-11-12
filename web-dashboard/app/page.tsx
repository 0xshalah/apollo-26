import Link from 'next/link';
import { AppShell } from '@/components/AppShell';

export default function HomePage() {
  return (
    <AppShell current="home">
      <main id="main" className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
        <h1 className="font-display text-5xl leading-tight sm:text-6xl">Apollo-26</h1>
        <p className="mt-4 max-w-prose text-electrum/80">
          An emergency command path without an IP interface: the ground station transmits authenticated 300-baud
          Bell-202 frames as sound, the local daemon validates them, and a Kiro Flight Watch session plans DSKY input
          through the MCP safety gate for an AGC-faithful subset emulator (P00 and simplified P40).
        </p>
        <ul className="mt-10 grid gap-px border border-electrum/15 bg-electrum/15 sm:grid-cols-2">
          <li className="bg-lunar-900">
            <Link href="/ground/" className="block min-h-11 p-6 hover:bg-lunar-800">
              <span className="block font-display text-3xl">Ground station</span>
              <span className="mt-2 block text-sm text-electrum/75">
                Compose, sign, inspect, and transmit COMMAND and AUTH frames.
              </span>
            </Link>
          </li>
          <li className="bg-lunar-900">
            <Link href="/console/" className="block min-h-11 p-6 hover:bg-lunar-800">
              <span className="block font-display text-3xl">Mission console</span>
              <span className="mt-2 block text-sm text-electrum/75">
                Read-only DSKY, spectrum, frame audit, and status from the local daemon.
              </span>
            </Link>
          </li>
        </ul>
        <p className="mt-8 text-xs text-electrum/70">
          The emulator does not run Luminary or Colossus flight software. Kiro uses a cloud LLM; only the
          daemon–MCP–AGC command path is local.
        </p>
      </main>
    </AppShell>
  );
}
