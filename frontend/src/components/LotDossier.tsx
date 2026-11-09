'use client';

import Link from 'next/link';
import { useState } from 'react';
import { LedgerItem, ledgerOf, Lot, lotHeadline, LotPraca } from './LotCard';
import { API_URL, formatMoney, httpUrl } from '../lib/api';

function formatStamp(iso?: string): string | null {
  if (!iso || iso.length < 10) return null;
  const [date, time] = iso.split('T');
  const [year, month, day] = date.split('-');
  if (!year || !month || !day) return null;
  const hhmm = (time || '').slice(0, 5);
  if (!hhmm || hhmm === '00:00') return `${day}/${month}/${year}`;
  return `${day}/${month}/${year} ${hhmm}`;
}

function pracaWhen(praca: LotPraca): string {
  const start = formatStamp(praca.inicio);
  const end = formatStamp(praca.fim);
  if (start && end && start !== end) return `${start} – ${end}`;
  return start || end || 'Data não publicada';
}

function verdict(lot: Lot): { title: string; body: string; tone: 'go' | 'stop' | 'wait' } {
  if (lot.veredito === 'nao_aprofundar' || lot.nao_entrar || lot.riscos?.citacao === 'nao_citado' || lot.riscos?.citacao === 'pendente') {
    return {
      title: lot.veredito_titulo || 'Não aprofundar',
      body: lot.veredito_corpo || 'Citação não feita. O arremate não segura.',
      tone: 'stop',
    };
  }
  if (lot.veredito === 'aprofundar') {
    return {
      title: lot.veredito_titulo || 'Aprofundar',
      body: lot.veredito_corpo || 'Há indício. Ler o dossiê — não é decisão de lance.',
      tone: 'go',
    };
  }
  if (lot.veredito === 'falta_peca' || !lot.avaliado_em) {
    return {
      title: lot.veredito_titulo || (lot.avaliado_em ? 'Falta peça' : 'Ainda sem leitura'),
      body: lot.veredito_corpo || 'Falta edital, matrícula ou laudo para afirmar o indício.',
      tone: 'wait',
    };
  }
  return {
    title: 'Falta peça',
    body: 'Não há vantagem com dado. Falta documento para apontar o indício.',
    tone: 'wait',
  };
}

function LedgerList({ itens, lado }: { itens: LedgerItem[]; lado: LedgerItem['lado'] }) {
  const rows = itens.filter((i) => i.lado === lado);
  if (!rows.length) return null;
  return (
    <ul className="ledger-list">
      {rows.map((item) => (
        <li key={`${item.id}-${item.titulo}`}>
          <strong>{item.titulo}</strong>
          {item.metrica ? <span> · {item.metrica}</span> : null}
          <p>{item.frase}</p>
          {item.trecho ? <blockquote className="trecho">«{item.trecho}»</blockquote> : null}
        </li>
      ))}
    </ul>
  );
}

function parecerParagrafos(text: string): string[] {
  const trimmed = text.trim();
  if (!trimmed || trimmed.startsWith('{') || trimmed.startsWith('[') || trimmed.startsWith('```')) {
    return [];
  }
  const parts = text
    .split(/\n\s*\n/)
    .map((p) => p.replace(/\s+/g, ' ').trim())
    .filter(Boolean);
  return parts.length ? parts : [trimmed];
}

function pecaLida(d: { label?: string; tipo?: string; ocr?: boolean; scanned?: boolean; chars?: number }): string {
  const name = d.label || d.tipo || 'documento';
  const bits = [name];
  if (d.ocr) bits.push('OCR');
  else if (d.scanned) bits.push('sem texto');
  if (d.chars) bits.push(`${d.chars.toLocaleString('pt-BR')} caracteres`);
  return bits.join(' · ');
}

function fonteTrecho(t: { peca?: string; origem: string; ocr?: boolean; pagina?: number | string }): string {
  const bits: string[] = [];
  if (t.peca) bits.push(t.peca);
  else bits.push(ORIGEM_TRECHO[t.origem] || t.origem);
  if (t.ocr || t.origem === 'ocr') bits.push('OCR');
  if (t.pagina) bits.push(`p. ${t.pagina}`);
  return bits.join(', ');
}

function sourceLabel(source: string): string {
  const labels: Record<string, string> = {
    calil: 'Calil',
    vegas: 'Vegas',
    zuk: 'Zuk',
    mega: 'Mega',
    lance: 'Grupo Lance',
    trt5: 'TRT5',
  };
  return labels[source] || source;
}

const TIPO_TRECHO: Record<string, string> = {
  ocupacao: 'Ocupação',
  avaliacao: 'Avaliação',
  area: 'Área',
  citacao: 'Citação',
  meacao: 'Meação',
  usufruto: 'Usufruto',
  valor_causa: 'Valor da causa',
  peticao: 'Petição',
};

const ORIGEM_TRECHO: Record<string, string> = {
  pagina: 'página do leilão',
  edital: 'edital',
  laudo: 'laudo',
  matricula: 'matrícula',
  penhora: 'auto de penhora',
  ocr: 'OCR',
  anexo: 'anexo',
  infosimples: 'Infosimples',
};

export function LotDossier({ lot: initial }: { lot: Lot }) {
  const [lot, setLot] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const site = httpUrl(lot.url);
  const headline = lotHeadline(lot);
  const call = verdict(lot);
  const pracas = lot.pracas || [];
  const peticoes = lot.infosimples_peticoes_recentes || [];
  const trechos = lot.trechos || [];
  const temTrecho = (tipo: string) => trechos.some((t) => t.tipo === tipo);

  const solicitar = async () => {
    setBusy(true);
    setErro(null);
    try {
      const res = await fetch(`${API_URL}/api/lots/${lot.id}/avaliar`, { method: 'POST' });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'Falha ao avaliar');
      setLot(data as Lot);
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falha ao avaliar');
    } finally {
      setBusy(false);
    }
  };

  return (
    <article className="dossier">
      <Link className="dossier-back" href="/">
        ← Catálogo
      </Link>

      <header className="dossier-cover">
        {lot.foto ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={lot.foto} alt="" width={720} height={240} />
        ) : null}
        <div>
          <p className="dossier-kicker">
            {sourceLabel(lot.source)}
            {lot.cidade ? ` · ${lot.cidade}` : ''}
            {lot.processo_cnj ? ` · ${lot.processo_cnj}` : ''}
          </p>
          <h1>{headline}</h1>
          {lot.endereco ? <p className="muted">{lot.endereco}</p> : null}
          <div className="dossier-verdict" data-tone={call.tone === 'stop' ? 'stop' : call.tone === 'go' ? 'go' : undefined}>
            <strong>{call.title}</strong>
            <p>{call.body}</p>
          </div>
        </div>
      </header>

      <section className="dossier-section" aria-labelledby="pracas-title">
        <h2 id="pracas-title">Onde o leilão está</h2>
        {pracas.length ? (
          <ol className="praca-list">
            {pracas.map((praca) => (
              <li key={praca.n} data-ativa={praca.ativa ? 'true' : 'false'}>
                <span>{praca.n}ª praça</span>
                <span>{pracaWhen(praca)}</span>
                <span>
                  {praca.valor != null ? formatMoney(praca.valor) : '—'}
                  {praca.ativa ? <span className="praca-now"> agora</span> : null}
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="muted">
            Este anúncio ainda não trouxe 1ª e 2ª praça no HTML público. A avaliação tenta completar isso na
            página do bem.
          </p>
        )}
      </section>

      <section className="dossier-section" aria-labelledby="ledger-title">
        <h2 id="ledger-title">Indício</h2>
        <h3>A favor</h3>
        <LedgerList itens={ledgerOf(lot)} lado="vantagem" />
        {!ledgerOf(lot).some((i) => i.lado === 'vantagem') ? <p className="muted">Nenhuma vantagem com documento.</p> : null}
        <h3>Contra</h3>
        <LedgerList itens={ledgerOf(lot)} lado="veto" />
        <LedgerList itens={ledgerOf(lot)} lado="risco" />
        {!ledgerOf(lot).some((i) => i.lado === 'veto' || i.lado === 'risco') ? (
          <p className="muted">Nenhum risco com documento.</p>
        ) : null}
        <h3>O que falta</h3>
        <LedgerList itens={ledgerOf(lot)} lado="incerteza" />
        {!ledgerOf(lot).some((i) => i.lado === 'incerteza') ? <p className="muted">Nada além do que já está no ledger.</p> : null}
      </section>

      <section className="dossier-section" aria-labelledby="numeros-title">
        <h2 id="numeros-title">O que está em jogo</h2>
        <div className="money-row">
          <div>
            <span>Lance pedido</span>
            <strong>{formatMoney(lot.current_bid ?? lot.minimum_bid)}</strong>
          </div>
          <div>
            <span>{lot.avaliacao_fonte === 'venal_imovel' ? 'Venal (IPTU)' : 'Avaliação'}</span>
            <strong>{formatMoney(lot.avaliacao_edital ?? lot.reference_value)}</strong>
          </div>
          <div>
            <span>Ref. mercado</span>
            <strong>{formatMoney(lot.valor_mercado_estimado)}</strong>
          </div>
        </div>
        {lot.valor_m2_fonte === 'apify' && lot.valor_m2_n && lot.valor_mercado_estimado != null ? (
          <p className="muted">
            Mediana de {lot.valor_m2_n} anúncios de venda no Zap/VivaReal
            {lot.cidade ? ` em ${lot.cidade}` : ''}. Preço pedido, não transação (ITBI).
            {lot.tipo === 'terreno'
              ? ' O portal não filtra terreno nesta consulta — a amostra é o que está à venda na cidade.'
              : ''}
          </p>
        ) : lot.valor_m2_fonte === 'fipezap' && lot.valor_mercado_estimado != null ? (
          <p className="muted">Índice FipeZap de venda residencial (apartamento anunciado na cidade).</p>
        ) : lot.avaliado_em && lot.valor_mercado_estimado == null ? (
          <p className="muted">
            {lot.apify === 'ok' && lot.valor_m2_n
              ? 'O Zap trouxe anúncios, mas falta metragem no laudo/matrícula para converter em valor do imóvel.'
              : lot.apify === 'poucos'
              ? 'Zap/VivaReal não trouxe 3 anúncios de venda nesta cidade para montar a referência.'
              : lot.apify === 'indisponivel'
                ? 'A consulta de anúncios no Zap não respondeu nesta avaliação.'
                : lot.apify === 'sem_token'
                  ? 'Falta o token da Apify no servidor — sem ele a referência de mercado não consulta o Zap.'
                  : 'Sem índice FipeZap neste tipo/cidade. A referência depende de anúncios no Zap.'}
          </p>
        ) : null}
        {lot.ocupacao && temTrecho('ocupacao') ? <p>Ocupação no texto lido: {lot.ocupacao}.</p> : null}
        {typeof lot.dividas?.condominio === 'number' ? (
          <p>Condomínio {formatMoney(lot.dividas.condominio as number)} — obrigação propter rem; o edital diz se você paga.</p>
        ) : null}
        {typeof lot.dividas?.iptu === 'number' ? (
          <p>
            IPTU {formatMoney(lot.dividas.iptu as number)}
            {lot.regime === 'judicial'
              ? ' — no judicial o tributo anterior sub-roga no preço (Tema 1.134/STJ).'
              : lot.regime === 'extrajudicial'
                ? ' — no extrajudicial o edital costuma atribuir o IPTU ao arrematante.'
                : lot.regime === 'trabalhista'
                  ? ' — conferir no edital do tribunal; não herdar a regra cível.'
                  : ' — sem regime do leilão, não dá para dizer se fica com o arrematante.'}
          </p>
        ) : null}
      </section>

      <section className="dossier-section" aria-labelledby="processo-title">
        <h2 id="processo-title">Processo e Infosimples</h2>
        {lot.processo_cnj ? <p>CNJ {lot.processo_cnj}.</p> : <p className="muted">Sem número de processo no anúncio.</p>}
        {lot.infosimples_valor_causa != null ? (
          <p>
            Valor da causa que originou a execução: {formatMoney(lot.infosimples_valor_causa)}. Isso é a dívida
            original, não o valor do imóvel.
          </p>
        ) : lot.infosimples === 'ok' ? (
          <p className="muted">Infosimples leu o processo, sem valor da causa neste retorno.</p>
        ) : lot.avaliado_em ? (
          <p className="muted">Infosimples só cobre TJSP, uma vez por processo, na avaliação sob demanda.</p>
        ) : null}
        {lot.infosimples_foro ? (
          <p className="muted">
            {lot.infosimples_foro}
            {lot.infosimples_vara ? ` · ${lot.infosimples_vara}` : ''}
          </p>
        ) : null}
        {peticoes.length ? (
          <p>
            Petições recentes:{' '}
            {peticoes
              .map((p) => [p.tipo, p.data].filter(Boolean).join(' '))
              .join('; ')}
            .
          </p>
        ) : null}
        {lot.riscos?.citacao && temTrecho('citacao') ? (
          <p>
            Citação: {lot.riscos.citacao}
            {lot.riscos.citacao_fonte ? ` (${lot.riscos.citacao_fonte})` : ''}.
          </p>
        ) : null}
      </section>

      <section className="dossier-section" aria-labelledby="trechos-title">
        <h2 id="trechos-title">O que o documento diz</h2>
        {trechos.length ? (
          <ul className="trecho-list">
            {trechos.map((t) => (
              <li key={`${t.tipo}-${t.origem}`}>
                <blockquote className="trecho">
                  <p>«{t.texto}»</p>
                  <footer>
                    {TIPO_TRECHO[t.tipo] || t.tipo}
                    {' · '}
                    {fonteTrecho(t)}
                  </footer>
                </blockquote>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">
            Sem trecho citável ainda. A avaliação só afirma ocupação, meação ou citação quando acha a frase no
            documento.
          </p>
        )}
      </section>

      <section className="dossier-section" aria-labelledby="parecer-title">
        <h2 id="parecer-title">Parecer</h2>
        {lot.parecer && parecerParagrafos(lot.parecer).length ? (
          parecerParagrafos(lot.parecer).map((p, i) => <p key={i}>{p}</p>)
        ) : (
          <p className="muted">
            {lot.parecer
              ? 'O parecer veio em formato inválido. Vale o indício acima, não aquele bloco.'
              : 'Ainda não há parecer. Peça a avaliação.'}
          </p>
        )}
        {lot.docs?.length ? (
          <p className="muted">
            Peças lidas:{' '}
            {lot.docs.slice(0, 6).map(pecaLida).filter(Boolean).join('; ')}.
          </p>
        ) : null}
      </section>

      <section className="dossier-section">
        <h2>Decidir</h2>
        <p className="muted">
          Esta página organiza o que já está público. O lance continua no site do leiloeiro.
        </p>
        <div className="dossier-actions">
          <button type="button" className="btn" onClick={solicitar} disabled={busy} aria-busy={busy}>
            {busy ? 'Lendo documentos…' : lot.avaliado_em ? 'Atualizar avaliação' : 'Solicitar avaliação'}
          </button>
          {site ? (
            <a className="btn btn-secondary" href={site} target="_blank" rel="noopener noreferrer">
              Abrir no leiloeiro
            </a>
          ) : null}
        </div>
        {erro ? <p className="msg msg-error">{erro}</p> : null}
      </section>
    </article>
  );
}
