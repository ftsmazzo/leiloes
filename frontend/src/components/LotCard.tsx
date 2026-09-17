import { formatMoney, httpUrl } from '../lib/api';

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
  valor_m2_regiao: number | null;
  valor_mercado_estimado: number | null;
  score: number | null;
  score_tem_comparacao_preco: boolean | null;
  score_motivos: string[];
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

export function lotHeadline(lot: Lot): string {
  if (lot.headline) return lot.headline;
  const tipo = lot.tipo ? TIPO_LABELS[lot.tipo] || lot.tipo : null;
  return [tipo, lot.bairro, lot.cidade].filter(Boolean).join(' · ') || 'Lote';
}

export type ScoreTier = 'alto' | 'baixo' | 'neutro' | 'sem-preco';

export function scoreTier(lot: Lot): ScoreTier {
  if (lot.score == null) return 'neutro';
  if (!lot.score_tem_comparacao_preco) return 'sem-preco';
  if (lot.score >= 65) return 'alto';
  if (lot.score <= 35) return 'baixo';
  return 'neutro';
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
        <div className="lot-card-head">
          <span className="source-tag">{lot.source}</span>
          {lot.score != null ? (
            <span
              className="score-badge"
              data-tier={scoreTier(lot)}
              title={lot.score_tem_comparacao_preco ? 'Score de oportunidade' : 'Score parcial — sem referência de preço pra comparar'}
            >
              {lot.score}
            </span>
          ) : null}
        </div>
        <h2>{headline}</h2>
        {lot.score_motivos.length > 0 ? (
          <ul className="lot-motivos">
            {lot.score_motivos.slice(0, 2).map((motivo) => (
              <li key={motivo}>{motivo}</li>
            ))}
          </ul>
        ) : null}
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
          {lot.valor_mercado_estimado != null ? (
            <>
              <dt>Ref. mercado</dt>
              <dd title={lot.valor_m2_regiao != null ? `${formatMoney(lot.valor_m2_regiao)}/m² na região` : undefined}>
                {formatMoney(lot.valor_mercado_estimado)}
              </dd>
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
