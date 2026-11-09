'use client';

import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { Lot } from '../components/LotCard';
import { LotRow } from '../components/LotRow';
import { API_URL } from '../lib/api';

type Source = { id: string; label: string };

type Leitura = {
  dias: number;
  com_peca: number;
  sem_peca: number;
  ocr_vazio: number;
};

type Facets = {
  total_lots: number;
  with_cidade: number;
  by_source: Record<string, number>;
  cidades: [string, number][];
  tipos: [string, number][];
  extract?: { gliner: boolean; openrouter: boolean; extract_model: string };
};

type ScrapeSummary = {
  total_auctions: number;
  total_lots: number;
  by_source?: Record<string, { auctions: number; lots: number }>;
  errors?: { source: string; error: string }[];
};

type ScrapeStatus = {
  status: 'idle' | 'running' | 'done' | 'error';
  summary: ScrapeSummary | null;
  error: string | null;
  current_source: string | null;
};

const TIPOS = [
  { id: '', label: 'Todos' },
  { id: 'imovel', label: 'Imóvel' },
  { id: 'casa', label: 'Casa' },
  { id: 'apartamento', label: 'Apartamento' },
  { id: 'terreno', label: 'Terreno' },
  { id: 'galpao', label: 'Galpão' },
  { id: 'chacara', label: 'Chácara' },
  { id: 'sala', label: 'Sala' },
];

const SCRAPE_POLL_MS = 1500;
const SCRAPE_MAX_WAIT_MS = 5 * 60_000;

export default function Home() {
  const [sources, setSources] = useState<Source[]>([]);
  const [source, setSource] = useState('');
  const [cidade, setCidade] = useState('');
  const [tipo, setTipo] = useState('imovel');
  const [teto, setTeto] = useState('');
  const [q, setQ] = useState('');
  const [applied, setApplied] = useState({ cidade: '', tipo: 'imovel', teto: '', q: '' });
  const [sortByScore, setSortByScore] = useState(true);
  const [lots, setLots] = useState<Lot[]>([]);
  const [facets, setFacets] = useState<Facets | null>(null);
  const [leitura, setLeitura] = useState<Leitura | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [scrapeLoading, setScrapeLoading] = useState(false);
  const [scrapeResult, setScrapeResult] = useState<ScrapeSummary | null>(null);
  const [scrapeError, setScrapeError] = useState<string | null>(null);
  const [scrapeSource, setScrapeSource] = useState<string | null>(null);
  const cancelledRef = useRef(false);

  const cityOptions = useMemo(() => facets?.cidades ?? [], [facets]);
  const filterCount = [source, applied.cidade, applied.tipo, applied.teto, applied.q].filter(Boolean).length;

  useEffect(
    () => () => {
      cancelledRef.current = true;
    },
    [],
  );

  useEffect(() => {
    const ac = new AbortController();
    fetch(`${API_URL}/api/sources`, { signal: ac.signal })
      .then((r) => (r.ok ? r.json() : []))
      .then((data: Source[]) => {
        if (Array.isArray(data) && data.length) setSources(data);
      })
      .catch((e) => {
        if (e instanceof Error && e.name === 'AbortError') return;
      });
    return () => ac.abort();
  }, []);

  useEffect(() => {
    const ac = new AbortController();
    setLoading(true);
    const params = new URLSearchParams();
    if (source) params.set('source', source);
    if (applied.cidade) params.set('cidade', applied.cidade);
    if (applied.tipo) params.set('tipo', applied.tipo);
    if (applied.teto) params.set('teto', applied.teto);
    if (applied.q) params.set('q', applied.q);
    if (sortByScore) params.set('sort', 'score');
    params.set('limit', '80');
    Promise.all([
      fetch(`${API_URL}/api/lots?${params}`, { signal: ac.signal }),
      fetch(`${API_URL}/api/facets`, { signal: ac.signal }),
      fetch(`${API_URL}/api/stats`, { signal: ac.signal }),
    ])
      .then(async ([lotsRes, facetsRes, statsRes]) => {
        if (!lotsRes.ok) throw new Error('Falha ao carregar lotes');
        setLots(await lotsRes.json());
        setFacets(facetsRes.ok ? await facetsRes.json() : null);
        const stats = statsRes.ok ? await statsRes.json() : null;
        setLeitura(stats?.leitura ?? null);
        setError(null);
      })
      .catch((e) => {
        if (e instanceof Error && e.name === 'AbortError') return;
        const msg = e instanceof Error ? e.message : 'Falha ao carregar';
        setError(msg === 'Failed to fetch' ? `Não foi possível conectar à API em ${API_URL}.` : msg);
        setLots([]);
      })
      .finally(() => {
        if (!ac.signal.aborted) setLoading(false);
      });
    return () => ac.abort();
  }, [source, applied, sortByScore, reloadToken]);

  const onSearch = (e: FormEvent) => {
    e.preventDefault();
    setApplied({ cidade: cidade.trim(), tipo, teto: teto.trim(), q: q.trim() });
  };

  const limpar = () => {
    setSource('');
    setCidade('');
    setTipo('');
    setTeto('');
    setQ('');
    setSortByScore(true);
    setApplied({ cidade: '', tipo: '', teto: '', q: '' });
  };

  const pollScrapeStatus = async (deadline: number) => {
    if (cancelledRef.current) return;
    let data: ScrapeStatus | null = null;
    try {
      const res = await fetch(`${API_URL}/api/run-scrape/status`);
      data = res.ok ? await res.json() : null;
    } catch {
      data = null;
    }
    if (cancelledRef.current) return;
    if (data) {
      setScrapeSource(data.current_source);
      if (data.status === 'done') {
        setScrapeResult(data.summary);
        setScrapeLoading(false);
        setScrapeSource(null);
        setReloadToken((n) => n + 1);
        return;
      }
      if (data.status === 'error') {
        setScrapeError(data.error || 'Falha ao rodar scrape');
        setScrapeLoading(false);
        setScrapeSource(null);
        return;
      }
    }
    if (Date.now() > deadline) {
      setScrapeError('Scrape demorou demais. Tente checar de novo em instantes.');
      setScrapeLoading(false);
      setScrapeSource(null);
      return;
    }
    setTimeout(() => pollScrapeStatus(deadline), SCRAPE_POLL_MS);
  };

  const runScrape = async () => {
    setScrapeLoading(true);
    setScrapeResult(null);
    setScrapeError(null);
    setScrapeSource(null);
    try {
      const res = await fetch(`${API_URL}/api/run-scrape`, { method: 'POST' });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'Falha ao rodar scrape');
      pollScrapeStatus(Date.now() + SCRAPE_MAX_WAIT_MS);
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Erro ao rodar scrape';
      setScrapeError(msg === 'Failed to fetch' ? `API fora. Suba o backend em ${API_URL}.` : msg);
      setScrapeLoading(false);
    }
  };

  return (
    <div className="grade" aria-busy={loading}>
      <details className="painel" open>
        <summary>
          Filtros {filterCount ? <span>({filterCount})</span> : null}
        </summary>
        <form id="form-filtros" onSubmit={onSearch} autoComplete="off">
          <div className="campo">
            <label className="rot" htmlFor="q">
              Buscar
            </label>
            <input
              id="q"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="rua, bairro, matrícula…"
            />
          </div>
          <div className="campo">
            <label className="rot" htmlFor="cidade">
              Cidade
            </label>
            <input
              id="cidade"
              value={cidade}
              onChange={(e) => setCidade(e.target.value)}
              placeholder="Ribeirão Preto"
              list="cidades"
            />
            <datalist id="cidades">
              {cityOptions.map(([name]) => (
                <option key={name} value={name} />
              ))}
            </datalist>
          </div>
          <fieldset>
            <legend>Tipo de imóvel</legend>
            <div className="chips" role="radiogroup" aria-label="Tipo">
              {TIPOS.map((t) => (
                <label className="chip" key={t.id || 'all-tipo'}>
                  <input
                    type="radio"
                    name="tipo"
                    checked={tipo === t.id}
                    onChange={() => setTipo(t.id)}
                  />
                  <span>{t.label}</span>
                </label>
              ))}
            </div>
          </fieldset>
          <fieldset>
            <legend>Fonte</legend>
            <div className="chips" role="radiogroup" aria-label="Fonte">
              <label className="chip">
                <input type="radio" name="fonte" checked={source === ''} onChange={() => setSource('')} />
                <span>Todas</span>
              </label>
              {sources.map((s) => (
                <label className="chip" key={s.id}>
                  <input
                    type="radio"
                    name="fonte"
                    checked={source === s.id}
                    onChange={() => setSource(s.id)}
                  />
                  <span>
                    {s.label}
                    {facets?.by_source?.[s.id] != null ? ` (${facets.by_source[s.id]})` : ''}
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
          <div className="campo">
            <label className="rot" htmlFor="teto">
              Lance até (R$)
            </label>
            <input
              id="teto"
              value={teto}
              onChange={(e) => setTeto(e.target.value)}
              inputMode="numeric"
              placeholder="300000"
            />
          </div>
          <label className="marca">
            <input
              type="checkbox"
              checked={sortByScore}
              onChange={(e) => setSortByScore(e.target.checked)}
            />
            Ordenar por score
          </label>
          <button className="btn" type="submit">
            Filtrar
          </button>
          <button className="btn sec" type="button" onClick={limpar}>
            Limpar filtros
          </button>
          <button
            className="btn sec"
            type="button"
            onClick={runScrape}
            disabled={scrapeLoading}
            aria-busy={scrapeLoading}
          >
            {scrapeLoading ? `Atualizando${scrapeSource ? ` (${scrapeSource})` : '…'}` : 'Atualizar catálogo'}
          </button>
          {leitura ? (
            <p className="exemplo">
              Leitura · 7 dias: {leitura.com_peca} com peça · {leitura.sem_peca} sem peça · {leitura.ocr_vazio} OCR
              vazio
            </p>
          ) : null}
        </form>
      </details>

      <div>
        <div className="cab-lista">
          <div>
            <h1 aria-live="polite">
              {loading ? 'Carregando…' : `${lots.length} oportunidade${lots.length === 1 ? '' : 's'}`}
            </h1>
            <p>
              Filtre e escolha um imóvel. A análise completa abre no dossiê.
              {facets ? ` · ${facets.with_cidade}/${facets.total_lots} com cidade` : ''}
            </p>
          </div>
        </div>

        {scrapeError ? <p className="msg msg-error">{scrapeError}</p> : null}
        {scrapeResult ? (
          <p className="msg msg-ok">
            Catálogo atualizado: <strong>{scrapeResult.total_lots}</strong> lote(s)
            {scrapeResult.errors && scrapeResult.errors.length > 0
              ? ` · falha: ${scrapeResult.errors.map((e) => e.source).join(', ')}`
              : ''}
          </p>
        ) : null}
        {error ? <p className="msg msg-error">{error}</p> : null}

        {loading ? (
          <div className="lista" aria-busy="true">
            <p className="sr-only">Carregando lotes</p>
            <div className="lote skel" />
            <div className="lote skel" />
            <div className="lote skel" />
          </div>
        ) : null}

        {!loading && !error && lots.length === 0 ? (
          <div className="vazio">
            <p>Nenhum lote com esses filtros.</p>
            <button className="btn" type="button" onClick={runScrape} disabled={scrapeLoading}>
              Atualizar catálogo
            </button>
          </div>
        ) : null}

        {!loading && !error && lots.length > 0 ? (
          <div className="lista">
            {lots.map((lot) => (
              <LotRow key={lot.id} lot={lot} />
            ))}
          </div>
        ) : null}

        <details className="como">
          <summary>Como usar</summary>
          <ul>
            <li>
              <b>Filtrar.</b> Busca, cidade, tipo, fonte e teto de lance usam os lotes já gravados no banco.
            </li>
            <li>
              <b>Analisar.</b> Abre o dossiê do imóvel. A avaliação lê a página pública e os PDFs públicos.
            </li>
            <li>
              <b>Sem norte.</b> Sem matrícula, laudo ou penhora útil, o sistema não trata o lote como oportunidade.
            </li>
          </ul>
        </details>
      </div>
    </div>
  );
}
