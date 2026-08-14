import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Governed Memory Hub - Cockpit',
  description: 'Control Cockpit & System Health Monitor',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="antialiased selection:bg-indigo-500/30 selection:text-indigo-200">
        {children}
      </body>
    </html>
  );
}
