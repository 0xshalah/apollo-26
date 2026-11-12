import type { Metadata, Viewport } from 'next';
import { Atkinson_Hyperlegible_Mono, Host_Grotesk } from 'next/font/google';
import type { ReactNode } from 'react';
import './globals.css';

// next/font downloads these at build time and serves them from the export; no runtime font requests.
const hostGrotesk = Host_Grotesk({ weight: ['400', '500'], subsets: ['latin'], variable: '--font-host-grotesk', display: 'swap' });
const atkinsonMono = Atkinson_Hyperlegible_Mono({
  weight: ['400', '500'],
  subsets: ['latin'],
  variable: '--font-atkinson-mono',
  display: 'swap',
  // next/font has no metric overrides for this family; fall back to the plain ui-monospace stack.
  adjustFontFallback: false,
});

export const metadata: Metadata = {
  title: { default: 'Apollo-26', template: '%s · Apollo-26' },
  description: 'Apollo-26 acoustic ground station and mission console (AGC-faithful subset emulator).',
};

export const viewport: Viewport = {
  // oklch(10.5% 0.008 250) (paper-3) as sRGB hex for the browser UI.
  themeColor: '#0b0d10',
  width: 'device-width',
  initialScale: 1,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${hostGrotesk.variable} ${atkinsonMono.variable}`}>
      <body className="bg-paper font-sans text-ink">
        <a
          href="#main"
          className="absolute left-4 -top-20 z-50 rounded-pill bg-accent px-4 py-2 font-medium text-accent-ink focus-visible:top-4"
        >
          Skip to main content
        </a>
        {children}
      </body>
    </html>
  );
}
