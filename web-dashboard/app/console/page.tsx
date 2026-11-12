import type { Metadata } from 'next';
import { ConsoleClient } from '@/components/console/ConsoleClient';

export const metadata: Metadata = { title: 'Mission console' };

export default function ConsolePage() {
  return <ConsoleClient />;
}
