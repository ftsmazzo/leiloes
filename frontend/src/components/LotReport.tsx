'use client';

import { LedgerItem, ledgerOf, Lot, lotHeadline, LotPraca } from './LotCard';
import { formatMoney, httpUrl } from '../lib/api';

function formatStamp(iso?: string | null): string | null {
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

function verdict(lot: Lot): { title: string; body: string } {
  if (lot.veredito === 'nao_aprofundar' || lot.nao_entrar || lot.riscos?.citacao === 'nao_citado' || lot.riscos?.citacao === 'pendente') {
    return {
      title: lot.veredito_titulo || 'Não aprofundar',
      body: lot.veredito_corpo || 'Citação não feita. O arremate não segura.',
    };
  }
  if (lot.veredito === 'aprofundar') {
    return {
      title: lot.veredito_titulo || 'Aprofundar',
      body: lot.veredito_corpo || 'Há indício. Ler o dossiê — não é decisão de lance.',
    };
  }
  if (lot.veredito === 'falta_peca' || !lot.avaliado_em) {
    return {
      title: lot.veredito_titulo || (lot.avaliado_em ? 'Falta peça' : 'Ainda sem leitura'),
      body: lot.veredito_corpo || 'Falta edital, matrícula ou laudo para afirmar o indício.',
    };
  }
  return {
    title: 'Falta peça',
    body: 'Não há vantagem com dado. Falta documento para apontar o indício.',
  };
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

function fonteTrecho(t: { peca?: string; origem: string; ocr?: boolean; pagina?: number | string }): string {
  const bits: string[] = [];
  if (t.peca) bits.push(t.peca);
  else bits.push(ORIGEM_TRECHO[t.origem] || t.origem);
  if (t.ocr || t.origem === 'ocr') bits.push('OCR');
  if (t.pagina) bits.push(`p. ${t.pagina}`);
  return bits.join(', ');
}

function LedgerBlock({ title, itens }: { title: string; itens: LedgerItem[] }) {
  if (!itens.length) return null;
  return (
    <div className="report-block">
      <h3>{title}</h3>
      <ul className="report-ledger">
        {itens.map((item) => (
          <li key={`${item.id}-${item.titulo}`}>
            <strong>
              {item.titulo}
              {item.metrica ? ` · ${item.metrica}` : ''}
            </strong>
            <p>{item.frase}</p>
            {item.trecho ? <blockquote>«{item.trecho}»</blockquote> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

function moneyLine(label: string, value: number | null | undefined) {
  if (value == null) return null;
  return (
    <div className="report-money-item">
      <span>{label}</span>
      <strong>{formatMoney(value)}</strong>
    </div>
  );
}

/** Layout A4 só para impressão / Salvar como PDF — oculto na tela. */
export function LotReport({ lot }: { lot: Lot }) {
  const call = verdict(lot);
  const headline = lotHeadline(lot);
  const site = httpUrl(lot.url);
  const ledger = ledgerOf(lot);
  const pracas = lot.pracas || [];
  const trechos = lot.trechos || [];
  const peticoes = lot.infosimples_peticoes_recentes || [];
  const avaliado = formatStamp(lot.avaliado_em);
  const gerado = formatStamp(new Date().toISOString());
  const avalLabel = lot.avaliacao_fonte === 'venal_imovel' ? 'Venal (IPTU)' : 'Avaliação';
  const avalValor = lot.avaliacao_edital ?? lot.reference_value;
  const mercadoFonte =
    lot.valor_m2_fonte === 'apify' && lot.valor_m2_n
      ? `Zap/VivaReal · ${lot.valor_m2_n} anúncios`
      : lot.valor_m2_fonte === 'fipezap'
        ? 'FipeZap'
        : null;

  return (
    <div className="lot-report" aria-hidden="true">
      <header className="report-masthead">
        <p className="report-brand">Leilões · Relatório de indício</p>
        <p className="report-disclaimer">
          Organiza o que já está público. Não é decisão de lance nem parecer jurídico vinculante.
        </p>
        <p className="report-meta">
          {gerado ? `Gerado em ${gerado}` : null}
          {avaliado ? ` · Avaliado em ${avaliado}` : ' · Ainda sem avaliação sob demanda'}
          {lot.score != null ? ` · Score ${lot.score}` : null}
        </p>
      </header>

      <section className="report-section report-cover">
        <p className="report-kicker">
          {[sourceLabel(lot.source), lot.cidade, lot.processo_cnj].filter(Boolean).join(' · ')}
        </p>
        <h1>{headline}</h1>
        {lot.endereco ? <p className="report-addr">{lot.endereco}</p> : null}
        {lot.bairro || lot.matricula || lot.area ? (
          <p className="report-facts">
            {[lot.bairro ? `Bairro ${lot.bairro}` : null, lot.matricula ? `Matrícula ${lot.matricula}` : null, lot.area ? `Área ${lot.area}` : null]
              .filter(Boolean)
              .join(' · ')}
          </p>
        ) : null}
        {lot.foto ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img className="report-photo" src={lot.foto} alt="" />
        ) : null}
        <div className="report-verdict">
          <strong>{call.title}</strong>
          <p>{call.body}</p>
        </div>
      </section>

      <section className="report-section">
        <h2>O que está em jogo</h2>
        <div className="report-money">
          {moneyLine('Lance pedido', lot.current_bid ?? lot.minimum_bid)}
          {moneyLine(avalLabel, avalValor)}
          {moneyLine(
            mercadoFonte ? `Ref. mercado (${mercadoFonte})` : 'Ref. mercado',
            lot.valor_mercado_estimado,
          )}
        </div>
        {lot.valor_m2_regiao != null && lot.valor_mercado_estimado != null ? (
          <p className="report-note">{formatMoney(lot.valor_m2_regiao)}/m² na referência usada.</p>
        ) : null}
        {lot.ocupacao ? <p>Ocupação no texto lido: {lot.ocupacao}.</p> : null}
        {typeof lot.dividas?.condominio === 'number' ? (
          <p>Condomínio {formatMoney(lot.dividas.condominio as number)}.</p>
        ) : null}
        {typeof lot.dividas?.iptu === 'number' ? (
          <p>
            IPTU {formatMoney(lot.dividas.iptu as number)}
            {lot.regime ? ` · regime ${lot.regime}` : ''}.
          </p>
        ) : null}
      </section>

      {pracas.length ? (
        <section className="report-section">
          <h2>Praças</h2>
          <table className="report-table">
            <thead>
              <tr>
                <th>Praça</th>
                <th>Quando</th>
                <th>Valor</th>
              </tr>
            </thead>
            <tbody>
              {pracas.map((praca) => (
                <tr key={praca.n}>
                  <td>
                    {praca.n}ª{praca.ativa ? ' · agora' : ''}
                  </td>
                  <td>{pracaWhen(praca)}</td>
                  <td>{praca.valor != null ? formatMoney(praca.valor) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      <section className="report-section">
        <h2>Indício</h2>
        <LedgerBlock title="A favor" itens={ledger.filter((i) => i.lado === 'vantagem')} />
        <LedgerBlock
          title="Contra"
          itens={ledger.filter((i) => i.lado === 'veto' || i.lado === 'risco')}
        />
        <LedgerBlock title="O que falta" itens={ledger.filter((i) => i.lado === 'incerteza')} />
        {!ledger.length ? <p className="report-note">Sem itens no ledger ainda.</p> : null}
      </section>

      <section className="report-section">
        <h2>Processo</h2>
        {lot.processo_cnj ? <p>CNJ {lot.processo_cnj}.</p> : <p className="report-note">Sem CNJ no anúncio.</p>}
        {lot.infosimples_valor_causa != null ? (
          <p>Valor da causa (execução): {formatMoney(lot.infosimples_valor_causa)}.</p>
        ) : null}
        {lot.infosimples_foro ? (
          <p>
            {lot.infosimples_foro}
            {lot.infosimples_vara ? ` · ${lot.infosimples_vara}` : ''}
          </p>
        ) : null}
        {peticoes.length ? (
          <p>
            Petições recentes:{' '}
            {peticoes.map((p) => [p.tipo, p.data].filter(Boolean).join(' ')).join('; ')}.
          </p>
        ) : null}
        {lot.riscos?.citacao ? (
          <p>
            Citação: {lot.riscos.citacao}
            {lot.riscos.citacao_fonte ? ` (${lot.riscos.citacao_fonte})` : ''}.
          </p>
        ) : null}
        {lot.riscos?.usufruto ? <p>Usufruto apontado nos riscos.</p> : null}
        {lot.riscos?.meacao ? <p>Meação apontada nos riscos.</p> : null}
      </section>

      {trechos.length ? (
        <section className="report-section">
          <h2>O que o documento diz</h2>
          <ul className="report-trechos">
            {trechos.map((t) => (
              <li key={`${t.tipo}-${t.origem}`}>
                <blockquote>
                  <p>«{t.texto}»</p>
                  <footer>
                    {TIPO_TRECHO[t.tipo] || t.tipo} · {fonteTrecho(t)}
                  </footer>
                </blockquote>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="report-section">
        <h2>Parecer</h2>
        {lot.parecer && parecerParagrafos(lot.parecer).length ? (
          parecerParagrafos(lot.parecer).map((p, i) => <p key={i}>{p}</p>)
        ) : (
          <p className="report-note">
            {lot.parecer ? 'Parecer em formato inválido — vale o indício acima.' : 'Ainda sem parecer.'}
          </p>
        )}
        {lot.docs?.length ? (
          <p className="report-note">Peças lidas: {lot.docs.map(pecaLida).filter(Boolean).join('; ')}.</p>
        ) : null}
      </section>

      <footer className="report-footer">
        <p>
          Lote #{lot.id}
          {lot.external_id ? ` · ref. ${lot.external_id}` : null}
          {lot.tipo ? ` · ${lot.tipo}` : null}
          {lot.regime ? ` · ${lot.regime}` : null}
        </p>
        {site ? <p className="report-url">{site}</p> : null}
      </footer>
    </div>
  );
}
