'use client';

import Link from 'next/link';
import { formatMoney, httpUrl } from '../lib/api';
import { Lot, lotHeadline, scoreTier } from './LotCard';

function scoreClass(lot: Lot): string {
  const tier = scoreTier(lot);
  if (tier === 'alto') return 'ex';
  if (tier === 'neutro') return 'boa';
  if (tier === 'sem-preco') return 'mod';
  return 'fra';
}

export function LotRow({ lot }: { lot: Lot }) {
  const bid = lot.current_bid ?? lot.minimum_bid;
  const site = httpUrl(lot.url);
  const headline = lotHeadline(lot);
  const semNorte = !lot.avaliado_em || lot.veredito_titulo === 'Sem norte' || Boolean(lot.riscos?.docs_limitados);
  const score = !semNorte && lot.score != null ? lot.score : null;
  const parcial = !semNorte && lot.score != null && lot.cobertura != null && lot.cobertura < 0.5;
  const ref = lot.valor_mercado_estimado ?? lot.avaliacao_edital ?? lot.reference_value;
  const veredito =
    lot.veredito_titulo
    || (lot.veredito === 'aprofundar'
      ? 'Aprofundar'
      : lot.veredito === 'falta_peca'
        ? 'Falta peça'
        : lot.veredito === 'nao_aprofundar' || lot.nao_entrar
          ? 'Não aprofundar'
          : null);

  return (
    <article className="lote">
      <div className="scorebox">
        {score != null ? (
          <>
            <div
              className={`score ${scoreClass(lot)}`}
              style={{ ['--p' as string]: Math.max(0, Math.min(100, score)) }}
              title="Score de indício — não é decisão de lance"
            >
              <span>{parcial ? '·' : score}</span>
            </div>
            <small>{parcial ? 'Parcial' : scoreTier(lot) === 'alto' ? 'Alta' : scoreTier(lot) === 'baixo' ? 'Baixa' : 'Média'}</small>
          </>
        ) : (
          <>
            <div className="score fra" style={{ ['--p' as string]: 0 }} title="Sem norte">
              <span>—</span>
            </div>
            <small>Sem norte</small>
          </>
        )}
      </div>

      <div className="info">
        <p className="kicker">
          {lot.source}
          {lot.cidade ? ` · ${lot.cidade}` : ''}
          {lot.tipo ? ` · ${lot.tipo}` : ''}
        </p>
        <h3>
          <Link href={`/lote/${lot.id}`}>{headline}</Link>
        </h3>
        <div className="tags">
          {veredito ? (
            <span
              className={
                lot.veredito === 'aprofundar'
                  ? 'tag ok'
                  : lot.veredito === 'nao_aprofundar' || lot.nao_entrar
                    ? 'tag no'
                    : 'tag qm'
              }
            >
              {veredito}
            </span>
          ) : null}
          {lot.status === 'aguardando' ? <span className="tag">Ainda não abriu</span> : null}
        </div>
        {semNorte && lot.veredito_corpo ? <p className="meta">{lot.veredito_corpo}</p> : null}
        {!semNorte && lot.endereco ? <p className="meta">{lot.endereco}</p> : null}
      </div>

      <dl className="vals">
        <div className="forte">
          <dt>Lance</dt>
          <dd>{formatMoney(bid)}</dd>
        </div>
        <div>
          <dt>{lot.valor_mercado_estimado != null ? 'Ref. mercado' : 'Avaliação'}</dt>
          <dd>{formatMoney(ref)}</dd>
        </div>
      </dl>

      <div className="acao">
        <Link className="btn" href={`/lote/${lot.id}`}>
          Analisar
        </Link>
        {site ? (
          <a className="btn sec" href={site} target="_blank" rel="noopener noreferrer">
            No leiloeiro
          </a>
        ) : null}
      </div>
    </article>
  );
}
