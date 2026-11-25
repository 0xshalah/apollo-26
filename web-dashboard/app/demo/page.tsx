import type { Metadata } from 'next';
import { AppShell, type ShellSection } from '@/components/AppShell';
import { DemoClient } from '@/components/demo/DemoClient';

export const metadata: Metadata = { title: 'Browser demo' };

const SECTIONS: readonly ShellSection[] = [
  { id: 'ground', label: 'Ground station' },
  { id: 'agent', label: 'You are the agent' },
  { id: 'log', label: 'Daemon and gate log' },
  { id: 'dsky', label: 'DSKY' },
];

export default function DemoPage() {
  return (
    <AppShell current="demo" sections={SECTIONS}>
      <main id="main" className="min-w-0">
        <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-1 border-b border-rule bg-paper-3 px-4 py-3 sm:px-6">
          <h1 className="text-[1.35rem] text-ink">Browser demo</h1>
          <p className="max-w-prose text-xs text-muted">
            A simulation in this tab: no microphone, daemon, or Kiro agent. You play the agent. The canonical planner and
            the DSKY are TypeScript ports checked against vectors the Python code generates; frame validation shares the
            golden frame vectors; the safety gate and AUTH ledger follow the Python check order and have their own tests.
            The daemon&apos;s second guard before key presses is not simulated. Nothing here is a measurement.
          </p>
        </div>
        <div className="mx-auto max-w-[110rem] px-4 pb-10 sm:px-6">
          <DemoClient />
        </div>
      </main>
    </AppShell>
  );
}
