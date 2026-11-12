import type { Metadata } from 'next';
import { AppShell, type ShellSection } from '@/components/AppShell';
import { GroundClient } from '@/components/ground/GroundClient';

export const metadata: Metadata = { title: 'Ground station' };

const SECTIONS: readonly ShellSection[] = [
  { id: 'compose', label: 'Compose frame' },
  { id: 'keys', label: 'Signing keys' },
  { id: 'transmit', label: 'Sign and transmit' },
  { id: 'preview', label: 'Frame preview' },
];

export default function GroundPage() {
  return (
    <AppShell current="ground" sections={SECTIONS}>
      <main id="main" className="min-w-0">
        <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-1 border-b border-rule bg-paper-3 px-4 py-3 sm:px-6">
          <h1 className="text-[1.35rem] text-ink">Ground station</h1>
          <p className="max-w-prose text-xs text-muted">
            Builds a 34-byte acoustic frame v1 and transmits it at 300 baud (Bell-202, 1200/2200 Hz). The daemon decides
            whether a frame is accepted; this page only reports browser playback.
          </p>
        </div>
        <div className="mx-auto max-w-[110rem] px-4 pb-6 sm:px-6">
          <GroundClient />
        </div>
      </main>
    </AppShell>
  );
}
