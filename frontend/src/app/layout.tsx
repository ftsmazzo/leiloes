import { Archivo, IBM_Plex_Mono, Public_Sans } from 'next/font/google';
import './globals.css';

const display = Archivo({
  subsets: ['latin'],
  weight: ['500', '600', '700', '800'],
  variable: '--font-display',
  display: 'swap',
});

const body = Public_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-body',
  display: 'swap',
});

const data = IBM_Plex_Mono({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-data',
  display: 'swap',
});

export const metadata = {
  title: 'Radar de Leilões',
  description:
    'Filtre lotes de Calil, Vegas, Zuk, Mega, Grupo Lance e TRT5. Sem matrícula pública, não há análise confiável.',
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
              <svg viewBox="0 0 26 26" fill="none" aria-hidden="true">
                <rect x="9" y="2" width="14" height="8" rx="1.5" transform="rotate(35 16 6)" fill="currentColor" />
                <path d="M12 12 4 22" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                <path d="M13 24h12" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
              </svg>
              Radar de Leilões
            </a>
            <p className="stamp">Catálogo de trabalho · análise sob demanda</p>
          </header>
          <p className="aviso">
            <b>Norte analítico.</b> Filtre, escolha o imóvel e abra a análise. Sem matrícula, laudo ou penhora na
            página pública, o veredito fica Sem norte. Não substitui leitura do edital nem orientação jurídica.
          </p>
          <main>{children}</main>
        </div>
      </body>
    </html>
  );
}
