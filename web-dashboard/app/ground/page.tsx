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
      <main id="main" className="mx-auto max-w-[110rem] px-4 py-6 sm:px-6">
        <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2 border-b border-electrum/15 pb-4">
          <h1 className="font-display text-4xl sm:text-5xl">Ground station</h1>
          <p className="max-w-prose text-sm text-electrum/75">
            Builds a 34-byte acoustic frame v1 and transmits it at 300 baud (Bell-202, 1200/2200 Hz). The daemon decides
            whether a frame is accepted; this page only reports browser playback.
          </p>
        </div>
        <GroundClient />
      </main>
    </AppShell>
  );
}
