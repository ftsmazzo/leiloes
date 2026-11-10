import { JetBrains_Mono, Source_Sans_3, Source_Serif_4 } from 'next/font/google';
import './globals.css';

const display = Source_Serif_4({
  subsets: ['latin'],
  weight: ['600', '700'],
  variable: '--font-display',
  display: 'swap',
});

const body = Source_Sans_3({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-body',
  display: 'swap',
});

const data = JetBrains_Mono({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-data',
  display: 'swap',
});

export const metadata = {
  title: 'Farol — indício antes do lance',
  description:
    'Catálogo de imóveis em leilão judicial. Filtre, abra o dossiê e saiba se vale aprofundar — sem ficar no escuro.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pt-BR" className={`${display.variable} ${body.variable} ${data.variable}`}>
      <body>
        <div className="wrap">
          <header className="top">
            <a className="brand" href="/">
              Farol<span>.</span>
            </a>
            <p className="stamp">Catálogo · praça judicial</p>
          </header>
          <nav className="tabs" aria-label="Seções">
            <a className="tab on" href="/">
              Radar
            </a>
            <span className="tab" aria-disabled="true">
              Em análise
            </span>
            <span className="tab" aria-disabled="true">
              Arquivo
            </span>
          </nav>
          <p className="aviso">
            Indício com peças públicas — não substitui edital nem orientação jurídica. Sem matrícula, laudo ou
            penhora útil, o veredito fica Sem norte.
          </p>
          <main>{children}</main>
        </div>
      </body>
    </html>
  );
}
