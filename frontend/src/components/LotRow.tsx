'use client';

import Link from 'next/link';
import { formatMoney, httpUrl } from '../lib/api';
import { Lot, lotHeadline } from './LotCard';

function stampClass(lot: Lot, veredito: string | null): string {
  if (!veredito) return 'carimbo warn';
  if (lot.veredito === 'aprofundar') return 'carimbo';
  if (lot.veredito === 'nao_aprofundar' || lot.nao_entrar || veredito === 'Não aprofundar') return 'carimbo void';
  return 'carimbo warn';
}

export function LotRow({ lot }: { lot: Lot }) {
  const bid = lot.current_bid ?? lot.minimum_bid;
  const site = httpUrl(lot.url);
  const headline = lotHeadline(lot);
  const semNorte = !lot.avaliado_em || lot.veredito_titulo === 'Sem norte' || Boolean(lot.riscos?.docs_limitados);
  const ref = lot.valor_mercado_estimado ?? lot.avaliacao_edital ?? lot.reference_value;
  const veredito =
    lot.veredito_titulo
    || (lot.veredito === 'aprofundar'
      ? 'Aprofundar'
      : lot.veredito === 'falta_peca'
        ? 'Falta peça'
        : lot.veredito === 'nao_aprofundar' || lot.nao_entrar
          ? 'Não aprofundar'
          : semNorte
            ? 'Sem norte'
            : null);
  const stampLabel =
    veredito === 'Não aprofundar' ? 'VOID' : veredito || '—';

  const refLabel = lot.external_id || String(lot.id);

  return (
    <article className="lote">
      <div className="ref" title={refLabel}>
        {refLabel.length > 10 ? refLabel.slice(0, 8) : refLabel}
      </div>
      <div className="info">
        <h3>
          <Link href={`/lote/${lot.id}`}>{headline}</Link>
        </h3>
        <p className="meta">
          {[lot.source, lot.cidade, lot.tipo].filter(Boolean).join(' · ')}
          {lot.endereco && !semNorte ? ` · ${lot.endereco}` : ''}
          {site ? (
            <>
              {' · '}
              <a href={site} target="_blank" rel="noopener noreferrer">
                leiloeiro
              </a>
            </>
          ) : null}
        </p>
      </div>
      <div className="num forte">{formatMoney(bid)}</div>
      <div className="num">{formatMoney(ref)}</div>
      <div className="veredito">
        <span className={stampClass(lot, veredito)} title={veredito || undefined}>
          {stampLabel}
        </span>
      </div>
      <div className="acao">
        <Link className="btn" href={`/lote/${lot.id}`}>
          Dossiê
        </Link>
      </div>
    </article>
  );
}
