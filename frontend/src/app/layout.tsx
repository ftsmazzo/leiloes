import './globals.css';

export const metadata = {
  title: 'Leilões · Catálogo',
  description: 'Cards de lote Calil e Vegas com cidade, endereço, tipo e lance',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pt-BR">
      <body>
        <header className="site-header">
          <p className="brand">Leilões</p>
          <p>Catálogo de trabalho — Calil, Vegas, Zuk, Mega e Grupo Lance</p>
        </header>
        <main className="site-main">{children}</main>
      </body>
    </html>
  );
}
