import type { Metadata } from 'next';
import { AppHeader } from '@/components/AppHeader';
import { GroundClient } from '@/components/ground/GroundClient';

export const metadata: Metadata = { title: 'Ground station' };

export default function GroundPage() {
  return (
    <>
      <AppHeader current="ground" />
      <main id="main" className="mx-auto max-w-[110rem] px-4 py-6 sm:px-6">
        <h1 className="font-display text-4xl sm:text-5xl">Ground station</h1>
        <p className="mt-2 max-w-prose text-sm text-electrum/75">
          Builds a 34-byte acoustic frame v1 and transmits it at 300 baud (Bell-202, 1200/2200 Hz). The daemon decides
          whether a frame is accepted; this page only reports browser playback.
        </p>
        <GroundClient />
      </main>
    </>
  );
}
