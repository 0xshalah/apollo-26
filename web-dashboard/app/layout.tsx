import type { Metadata, Viewport } from 'next';
import { Italiana, Space_Mono, Syne } from 'next/font/google';
import type { ReactNode } from 'react';
import './globals.css';

// next/font downloads these at build time and serves them from the export; no runtime font requests.
const italiana = Italiana({ weight: '400', subsets: ['latin'], variable: '--font-italiana', display: 'swap' });
const syne = Syne({ subsets: ['latin'], variable: '--font-syne', display: 'swap' });
const spaceMono = Space_Mono({ weight: ['400', '700'], subsets: ['latin'], variable: '--font-space-mono', display: 'swap' });

export const metadata: Metadata = {
  title: { default: 'Apollo-26', template: '%s · Apollo-26' },
  description: 'Apollo-26 acoustic ground station and mission console (AGC-faithful subset emulator).',
};

export const viewport: Viewport = {
  themeColor: '#050608',
  width: 'device-width',
  initialScale: 1,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${italiana.variable} ${syne.variable} ${spaceMono.variable}`}>
      <body className="bg-void font-ui text-electrum">
        <a
          href="#main"
          className="absolute left-4 -top-20 z-50 bg-electrum px-4 py-2 font-ui text-void focus-visible:top-4"
        >
          Skip to main content
        </a>
        {children}
      </body>
    </html>
  );
}
