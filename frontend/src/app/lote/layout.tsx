import type { ReactNode } from 'react';
import { DM_Sans, Newsreader } from 'next/font/google';
import './dossier.css';

const ui = DM_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-dossier-ui',
  display: 'swap',
});

const display = Newsreader({
  subsets: ['latin'],
  weight: ['500', '600'],
  variable: '--font-dossier-display',
  display: 'swap',
  adjustFontFallback: false,
});

export default function LoteLayout({ children }: { children: ReactNode }) {
  return <div className={`dossier-shell ${ui.variable} ${display.variable}`}>{children}</div>;
}
