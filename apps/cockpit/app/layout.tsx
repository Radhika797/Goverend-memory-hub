import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Governed Memory Hub - Enterprise Cockpit',
  description: 'Enterprise Governance Cockpit & System Health Monitor',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased selection:bg-blue-600/20 selection:text-blue-900 bg-slate-50 text-slate-900">
        {children}
      </body>
    </html>
  );
}
