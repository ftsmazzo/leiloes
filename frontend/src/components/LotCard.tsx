'use client';

import { Fragment, useState } from 'react';
import Link from 'next/link';
import { API_URL, formatMoney, httpUrl } from '../lib/api';

export type LotDoc = {
  tipo?: string;
  label?: string;
  url?: string;
  scanned?: boolean;
  anexo?: boolean;
  ocr?: boolean;
  chars?: number;
  paginas?: number;
};

export type LotPraca = {
  n: number;
  inicio?: string;
  fim?: string;
  valor?: number;
  ativa?: boolean;
};

export type LotTrecho = {
  tipo: string;
  texto: string;
  origem: string;
  peca?: string;
  ocr?: boolean;
  pagina?: number | string;
};

export type LedgerItem = {
  id: string;
  lado: 'vantagem' | 'risco' | 'veto' | 'incerteza';
  titulo: string;
  frase: string;
  fonte?: string;
  metrica?: string;
  trecho?: string;
  pontos?: number;
  confianca?: string;
};

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
  valor_m2_fonte?: string | null;
  valor_m2_n?: number | null;
  apify?: string | null;
  valor_mercado_estimado: number | null;
  score: number | null;
  score_tem_comparacao_preco: boolean | null;
  score_motivos: string[];
  veredito?: 'nao_aprofundar' | 'falta_peca' | 'aprofundar' | null;
  veredito_titulo?: string | null;
  veredito_corpo?: string | null;
  regime?: string | null;
  cobertura?: number | null;
  ledger?: LedgerItem[];
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
    docs_limitados?: boolean;
  } | null;
  infosimples?: string | null;
  infosimples_foro?: string | null;
  infosimples_vara?: string | null;
  infosimples_valor_causa?: number | null;
  infosimples_peticoes_recentes?: { data?: string; tipo?: string }[];
  trechos?: LotTrecho[];
  pracas?: LotPraca[];
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

function formatPracaStamp(iso?: string): string | null {
  if (!iso || iso.length < 16) return null;
  const [date, time] = iso.split('T');
  const [year, month, day] = date.split('-');
  if (!year || !month || !day) return null;
  const hhmm = (time || '').slice(0, 5);
  if (!hhmm || hhmm === '00:00') return `${day}/${month}/${year}`;
  return `${day}/${month}/${year} ${hhmm}`;
}

function formatPracaLine(praca: LotPraca): string {
  const start = formatPracaStamp(praca.inicio);
  const end = formatPracaStamp(praca.fim);
  let when = '';
  if (start && end && start !== end) when = `${start} – ${end}`;
  else when = start || end || '';
  const money = praca.valor != null ? formatMoney(praca.valor) : '';
  return [when, money].filter(Boolean).join(' · ');
}

function formatLaudoDate(iso: string): string {
  const stamp = Date.parse(`${iso.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(stamp)) return iso;
  const when = new Date(stamp);
  const years = Math.max(0, Math.round((Date.now() - stamp) / (365.25 * 24 * 3600 * 1000)));
  const month = String(when.getMonth() + 1).padStart(2, '0');
  if (years < 1) return `${month}/${when.getFullYear()}`;
  const label = years === 1 ? 'laudo de 1 ano' : `laudo de ${years} anos`;
  return `${month}/${when.getFullYear()} · ${label}`;
}

function laudoIdade(iso?: string | null): string | null {
  if (!iso) return null;
  const stamp = Date.parse(`${iso.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(stamp)) return null;
  const years = Math.floor((Date.now() - stamp) / (365.25 * 24 * 3600 * 1000));
  if (years < 1) return null;
  return years === 1 ? 'laudo de 1 ano' : `laudo de ${years} anos`;
}

const RE_OCUP_HEDGE = /caso\s+(?:o\s+)?im[oó]vel\s+esteja/i;
const RE_MEACAO_PRACA = /50\s*%\s+da\s+avalia/i;
const RE_MEACAO_PALAVRA = /mea[cç][aã]o|metade\s+(?:do\s+im[oó]vel|da\s+propriedade)/i;

function cardTrecho(lot: Lot): string | undefined {
  const escolhido = (lot.trechos || []).find((item) => {
    const txt = item.texto || '';
    if (!txt) return false;
    if (item.tipo === 'ocupacao' && RE_OCUP_HEDGE.test(txt)) return false;
    if (item.tipo === 'meacao' && RE_MEACAO_PRACA.test(txt) && !RE_MEACAO_PALAVRA.test(txt)) return false;
    return true;
  });
  if (escolhido?.texto) return escolhido.texto;
  const meacao = lot.riscos?.meacao_trecho;
  if (meacao && !(RE_MEACAO_PRACA.test(meacao) && !RE_MEACAO_PALAVRA.test(meacao))) return meacao;
  return undefined;
}

export type ScoreTier = 'alto' | 'baixo' | 'neutro' | 'sem-preco';

export function scoreTier(lot: Lot): ScoreTier {
  if (lot.veredito === 'nao_aprofundar' || lot.nao_entrar || lot.riscos?.citacao === 'nao_citado' || lot.riscos?.citacao === 'pendente') {
    return 'baixo';
  }
  if (lot.score == null) return 'neutro';
  if ((lot.cobertura != null && lot.cobertura < 0.5) || !lot.score_tem_comparacao_preco) return 'sem-preco';
  if (lot.score >= 65) return 'alto';
  if (lot.score <= 35) return 'baixo';
  return 'neutro';
}

export function ledgerOf(lot: Lot): LedgerItem[] {
  return Array.isArray(lot.ledger) ? lot.ledger : [];
}

export function pickLedger(lot: Lot, lado: LedgerItem['lado']): LedgerItem | undefined {
  return ledgerOf(lot).find((i) => i.lado === lado);
}

export function LotCard({ lot, onUpdated }: { lot: Lot; onUpdated?: (lot: Lot) => void }) {
  const site = httpUrl(lot.url);
  const bid = lot.current_bid ?? lot.minimum_bid;
  const headline = lotHeadline(lot);
  const semNorte = !lot.avaliado_em || lot.veredito_titulo === 'Sem norte' || Boolean(lot.riscos?.docs_limitados);
  const idadeLaudo = lot.avaliacao_fonte === 'venal_imovel' ? null : laudoIdade(lot.avaliacao_data);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [anexos, setAnexos] = useState<File[]>([]);

  const solicitar = async () => {
    setBusy(true);
    setErro(null);
    try {
      const opts: RequestInit = { method: 'POST' };
      if (anexos.length) {
        const body = new FormData();
        anexos.slice(0, 3).forEach((file) => body.append('anexos', file));
        opts.body = body;
      }
      const res = await fetch(`${API_URL}/api/lots/${lot.id}/avaliar`, opts);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'Falha ao avaliar');
      onUpdated?.(data as Lot);
      setAnexos([]);
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
          {lot.veredito || lot.nao_entrar ? (
            <span
              className="risk-tag"
              data-veredito={lot.veredito || (lot.nao_entrar ? 'nao_aprofundar' : undefined)}
            >
              {lot.veredito_titulo
                || (lot.veredito === 'aprofundar'
                  ? 'Aprofundar'
                  : lot.veredito === 'falta_peca'
                    ? 'Falta peça'
                    : 'Não aprofundar')}
            </span>
          ) : null}
          {!semNorte && lot.score != null && (lot.cobertura == null || lot.cobertura >= 0.5) ? (
            <span
              className="score-badge"
              data-tier={scoreTier(lot)}
              title="Score de indício — não é decisão de lance"
            >
              {lot.score}
            </span>
          ) : !semNorte && lot.score != null ? (
            <span className="score-badge" data-tier="sem-preco" title="Score parcial — cobertura baixa">
              parcial
            </span>
          ) : null}
        </div>
        {semNorte && lot.veredito_corpo ? <p className="sem-norte">{lot.veredito_corpo}</p> : null}
        <h2>
          <Link href={`/lote/${lot.id}`}>{headline}</Link>
        </h2>
        {(() => {
          const preco = ledgerOf(lot).find((i) => i.id === 'V1');
          const vantagem = preco?.lado === 'vantagem' ? preco : pickLedger(lot, 'vantagem');
          const risco =
            pickLedger(lot, 'veto')
            || (preco?.lado === 'risco' ? preco : pickLedger(lot, 'risco'));
          if (!vantagem && !risco) return null;
          return (
            <ul className="lot-ledger">
              {vantagem ? (
                <li data-lado="vantagem">
                  {vantagem.metrica ? `${vantagem.metrica} · ` : ''}
                  {vantagem.titulo}
                </li>
              ) : null}
              {risco ? (
                <li data-lado="risco">
                  {risco.metrica ? `${risco.metrica} · ` : ''}
                  {risco.titulo}
                </li>
              ) : null}
            </ul>
          );
        })()}
        {cardTrecho(lot) ? <p className="lot-trecho">«{cardTrecho(lot)}»</p> : null}
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
              <dd>
                {formatMoney(lot.reference_value)}
                {idadeLaudo ? ` · ${idadeLaudo}` : ''}
              </dd>
            </>
          ) : null}
          {(lot.pracas || []).map((praca) => {
            const line = formatPracaLine(praca);
            if (!line) return null;
            const label = (lot.pracas || []).length === 1 ? 'Praça' : `${praca.n}ª praça`;
            return (
              <Fragment key={praca.n}>
                <dt>{label}</dt>
                <dd>
                  {line}
                  {praca.ativa ? ' · agora' : ''}
                </dd>
              </Fragment>
            );
          })}
          {lot.avaliacao_data ? (
            <>
              <dt>{lot.avaliacao_data_origem === 'processo' ? 'Processo desde' : 'Data do laudo'}</dt>
              <dd>{formatLaudoDate(lot.avaliacao_data)}</dd>
            </>
          ) : null}
          {lot.valor_mercado_estimado != null ? (
            <>
              <dt>Ref. mercado</dt>
              <dd
                title={
                  lot.valor_m2_regiao != null
                    ? `${formatMoney(lot.valor_m2_regiao)}/m² · ${
                        lot.valor_m2_fonte === 'apify'
                          ? `${lot.valor_m2_n || ''} anúncios Zap/VivaReal`.trim()
                          : 'FipeZap'
                      }`
                    : undefined
                }
              >
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
          {lot.ocupacao && (lot.trechos || []).some((t) => t.tipo === 'ocupacao') ? (
            <>
              <dt>Ocupação</dt>
              <dd>{lot.ocupacao}</dd>
            </>
          ) : null}
          {typeof lot.dividas?.condominio === 'number' ? (
            <>
              <dt>Condomínio</dt>
              <dd>{formatMoney(lot.dividas.condominio as number)} · propter rem</dd>
            </>
          ) : null}
          {typeof lot.dividas?.iptu === 'number' ? (
            <>
              <dt>IPTU</dt>
              <dd>{formatMoney(lot.dividas.iptu as number)} · conferir regime</dd>
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
                    {doc.ocr ? ' · OCR' : ''}
                  </a>
                </li>
              ) : (
                <li key={doc.label || doc.tipo}>
                  {doc.label || doc.tipo || 'Anexo'}
                  {doc.anexo ? ' · anexo' : ''}
                  {doc.ocr ? ' · OCR' : ''}
                </li>
              ),
            )}
          </ul>
        ) : null}
        <div className="lot-card-actions">
          <label className="lot-anexo">
            <span className="lot-anexo-label">Anexar matrícula/laudo</span>
            <input
              type="file"
              accept="application/pdf,.pdf"
              multiple
              disabled={busy}
              onChange={(e) => setAnexos(Array.from(e.target.files || []).slice(0, 3))}
            />
            {anexos.length ? (
              <span className="lot-anexo-files">
                {anexos.map((f) => f.name).join(', ')}
              </span>
            ) : null}
          </label>
          <button type="button" className="btn btn-secondary" onClick={solicitar} disabled={busy} aria-busy={busy}>
            {busy ? 'Lendo documentos…' : lot.avaliado_em ? 'Atualizar avaliação' : 'Solicitar avaliação'}
          </button>
          {site ? (
            <a className="lot-card-link" href={site} target="_blank" rel="noopener noreferrer">
              Abrir no site
            </a>
          ) : null}
          <Link className="lot-card-link" href={`/lote/${lot.id}`}>
            Analisar
          </Link>
        </div>
        {erro ? <p className="msg msg-error">{erro}</p> : null}
      </div>
    </article>
  );
}
