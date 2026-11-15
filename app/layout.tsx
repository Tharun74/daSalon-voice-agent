import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'Glow Studio — A little time for you', description: 'An illustrative salon experience powered by da Salon. Explore services and speak with our AI concierge.' };
export default function Layout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}
