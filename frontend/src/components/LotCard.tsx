'use client';

import { useState } from 'react';
import { API_URL, formatMoney, httpUrl } from '../lib/api';

export type LotDoc = { tipo?: string; label?: string; url?: string; scanned?: boolean };

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
  parecer?: string | null;
  ocupacao?: string | null;
  avaliado_em?: string | null;
  docs?: LotDoc[];
  dividas: Record<string, unknown> | null;
  avaliacao_edital: number | null;
  avaliacao_fonte?: string | null;
  avaliacao_data?: string | null;
  avaliacao_data_origem?: string | null;
  status?: string | null;
  processo_cnj?: string | null;
  nao_entrar?: boolean | null;
  riscos?: {
    citacao?: string;
    citacao_fonte?: string;
    usufruto?: boolean;
    meacao?: boolean;
    meacao_trecho?: string;
    nao_entrar?: boolean;
    processo_cnj?: string;
  } | null;
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

function formatLaudoDate(iso: string): string {
  const stamp = Date.parse(`${iso.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(stamp)) return iso;
  const when = new Date(stamp);
  const years = Math.max(0, Math.round((Date.now() - stamp) / (365.25 * 24 * 3600 * 1000)));
  const month = String(when.getMonth() + 1).padStart(2, '0');
  const label = years === 1 ? '1 ano' : `${years} anos`;
  const opp = years >= 1 ? ' · oportunidade' : '';
  return `${month}/${when.getFullYear()} · ${label}${opp}`;
}

export type ScoreTier = 'alto' | 'baixo' | 'neutro' | 'sem-preco';

export function scoreTier(lot: Lot): ScoreTier {
  if (lot.nao_entrar || lot.riscos?.citacao === 'nao_citado' || lot.riscos?.citacao === 'pendente') {
    return 'baixo';
  }
  if (lot.score == null) return 'neutro';
  if (!lot.score_tem_comparacao_preco) return 'sem-preco';
  if (lot.score >= 65) return 'alto';
  if (lot.score <= 35) return 'baixo';
  return 'neutro';
}

export function LotCard({ lot, onUpdated }: { lot: Lot; onUpdated?: (lot: Lot) => void }) {
  const site = httpUrl(lot.url);
  const bid = lot.current_bid ?? lot.minimum_bid;
  const headline = lotHeadline(lot);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const solicitar = async () => {
    setBusy(true);
    setErro(null);
    try {
      const res = await fetch(`${API_URL}/api/lots/${lot.id}/avaliar`, { method: 'POST' });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'Falha ao avaliar');
      onUpdated?.(data as Lot);
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falha ao avaliar');
    } finally {
      setBusy(false);
    }
  };

  return (
    <article className="lot-card">
      {lot.foto ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img className="lot-card-photo" src={lot.foto} alt="" width={320} height={180} loading="lazy" />
      ) : null}
      <div className="lot-card-body">
        <div className="lot-card-head">
          <span className="source-tag">{lot.source}</span>
          {lot.status === 'aguardando' ? <span className="status-tag">Ainda não abriu</span> : null}
          {lot.nao_entrar || lot.riscos?.citacao === 'nao_citado' || lot.riscos?.citacao === 'pendente' ? (
            <span className="risk-tag">Não citado — não entrar</span>
          ) : null}
          {lot.riscos?.usufruto ? <span className="risk-tag">Usufruto</span> : null}
          {lot.riscos?.meacao ? <span className="risk-tag">Meação/fração</span> : null}
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
            {lot.score_motivos.slice(0, 5).map((motivo) => (
              <li key={motivo}>{motivo}</li>
            ))}
          </ul>
        ) : null}
        {lot.riscos?.meacao_trecho ? <p className="lot-trecho">Trecho: «{lot.riscos.meacao_trecho}»</p> : null}
        <dl className="lot-dl">
          {lot.processo_cnj ? (
            <>
              <dt>Processo</dt>
              <dd>{lot.processo_cnj}</dd>
            </>
          ) : null}
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
          <dt>
            {lot.minimum_bid != null && lot.current_bid != null && lot.current_bid > lot.minimum_bid * 1.05
              ? 'Lance atual'
              : 'Lance'}
          </dt>
          <dd>{formatMoney(bid)}</dd>
          {lot.minimum_bid != null && lot.current_bid != null && lot.current_bid > lot.minimum_bid * 1.05 ? (
            <>
              <dt>Lance inicial</dt>
              <dd>{formatMoney(lot.minimum_bid)}</dd>
            </>
          ) : null}
          {lot.reference_value != null ? (
            <>
              <dt>{lot.avaliacao_fonte === 'venal_imovel' ? 'Valor venal (IPTU)' : 'Avaliação'}</dt>
              <dd>{formatMoney(lot.reference_value)}</dd>
            </>
          ) : null}
          {lot.avaliacao_data ? (
            <>
              <dt>{lot.avaliacao_data_origem === 'processo' ? 'Processo desde' : 'Data do laudo'}</dt>
              <dd>{formatLaudoDate(lot.avaliacao_data)}</dd>
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
          {lot.ocupacao ? (
            <>
              <dt>Ocupação</dt>
              <dd>{lot.ocupacao}</dd>
            </>
          ) : null}
          {typeof lot.dividas?.condominio === 'number' ? (
            <>
              <dt>Condomínio</dt>
              <dd>{formatMoney(lot.dividas.condominio as number)} · não se abate</dd>
            </>
          ) : null}
          {typeof lot.dividas?.iptu === 'number' ? (
            <>
              <dt>IPTU</dt>
              <dd>{formatMoney(lot.dividas.iptu as number)} · em geral abatido</dd>
            </>
          ) : null}
        </dl>
        {lot.parecer ? <p className="lot-parecer">{lot.parecer}</p> : null}
        {lot.docs?.length ? (
          <ul className="lot-docs">
            {lot.docs.slice(0, 5).map((doc) =>
              doc.url ? (
                <li key={doc.url}>
                  <a href={doc.url} target="_blank" rel="noopener noreferrer">
                    {doc.label || doc.tipo || 'PDF'}
                  </a>
                </li>
              ) : null,
            )}
          </ul>
        ) : null}
        <div className="lot-card-actions">
          <button type="button" className="btn btn-secondary" onClick={solicitar} disabled={busy} aria-busy={busy}>
            {busy ? 'Lendo edital…' : lot.avaliado_em ? 'Atualizar avaliação' : 'Solicitar avaliação'}
          </button>
          {site ? (
            <a className="lot-card-link" href={site} target="_blank" rel="noopener noreferrer">
              Abrir no site
            </a>
          ) : null}
        </div>
        {erro ? <p className="msg msg-error">{erro}</p> : null}
      </div>
    </article>
  );
}
