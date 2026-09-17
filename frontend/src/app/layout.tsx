import './globals.css';

export const metadata = {
  title: 'Leilões Dashboard',
  description: 'Catálogo de lotes — Calil, Vegas e mais',
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
          <p>Catálogo por base — Calil, Vegas, Zuk, Mega e demo</p>
        </header>
        <main className="site-main">{children}</main>
      </body>
    </html>
  );
}
