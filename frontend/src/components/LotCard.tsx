export type Lot = {
  id: number;
  auction_id: number;
  external_id: string;
  source: string;
  title: string;
  category: string | null;
  tipo: string | null;
  headline: string | null;
  cidade: string | null;
  bairro: string | null;
  endereco: string | null;
  matricula: string | null;
  area: string | null;
  foto: string | null;
  current_bid: number | null;
  minimum_bid: number | null;
  reference_value: number | null;
  url: string | null;
};

const TIPO_LABELS: Record<string, string> = {
  apartamento: 'Apartamento',
  casa: 'Casa',
  terreno: 'Terreno',
  galpao: 'Galpão',
  chacara: 'Chácara',
  sala: 'Sala comercial',
  imovel: 'Imóvel',
  veiculo: 'Veículo',
};

export function formatMoney(value: number | null): string {
  if (value == null) return '—';
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 }).format(value);
}

export function httpUrl(url: string | null): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    if (parsed.protocol === 'http:' || parsed.protocol === 'https:') return url;
  } catch {
    return null;
  }
  return null;
}

export function lotHeadline(lot: Lot): string {
  if (lot.headline) return lot.headline;
  const tipo = lot.tipo ? TIPO_LABELS[lot.tipo] || lot.tipo : null;
  return [tipo, lot.bairro, lot.cidade].filter(Boolean).join(' · ') || 'Lote';
}

export function LotCard({ lot }: { lot: Lot }) {
  const site = httpUrl(lot.url);
  const bid = lot.current_bid ?? lot.minimum_bid;
  const headline = lotHeadline(lot);
  return (
    <article className="lot-card">
      {lot.foto ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img className="lot-card-photo" src={lot.foto} alt="" width={320} height={180} loading="lazy" />
      ) : null}
      <div className="lot-card-body">
        <span className="source-tag">{lot.source}</span>
        <h2>{headline}</h2>
        <dl className="lot-dl">
          {lot.endereco ? (
            <>
              <dt>Endereço</dt>
              <dd>{lot.endereco}</dd>
            </>
          ) : null}
          {lot.bairro && !headline.includes(lot.bairro) ? (
            <>
              <dt>Bairro</dt>
              <dd>{lot.bairro}</dd>
            </>
          ) : null}
          <dt>Lance</dt>
          <dd>{formatMoney(bid)}</dd>
          {lot.reference_value != null ? (
            <>
              <dt>Avaliação</dt>
              <dd>{formatMoney(lot.reference_value)}</dd>
            </>
          ) : null}
          {lot.matricula ? (
            <>
              <dt>Matrícula</dt>
              <dd>{lot.matricula}</dd>
            </>
          ) : null}
          {lot.area ? (
            <>
              <dt>Área</dt>
              <dd>{lot.area}</dd>
            </>
          ) : null}
        </dl>
        {site ? (
          <a className="lot-card-link" href={site} target="_blank" rel="noopener noreferrer">
            Abrir no site
          </a>
        ) : null}
      </div>
    </article>
  );
}
