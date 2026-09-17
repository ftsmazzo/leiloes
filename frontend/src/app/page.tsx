'use client';

import { FormEvent, useEffect, useMemo, useState } from 'react';
import { Lot, LotCard } from '../components/LotCard';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8050';

type Source = { id: string; label: string };

type Facets = {
  total_lots: number;
  with_cidade: number;
  by_source: Record<string, number>;
  cidades: [string, number][];
  tipos: [string, number][];
  extract?: { gliner: boolean; openrouter: boolean; extract_model: string };
};

type ScrapeResult = {
  status: string;
  total_auctions: number;
  total_lots: number;
  by_source?: Record<string, { auctions: number; lots: number }>;
  errors?: { source: string; error: string }[];
};

export default function Home() {
  const [sources, setSources] = useState<Source[]>([]);
  const [source, setSource] = useState('');
  const [cidade, setCidade] = useState('');
  const [tipo, setTipo] = useState('imovel');
  const [teto, setTeto] = useState('');
  const [q, setQ] = useState('');
  const [applied, setApplied] = useState({ cidade: '', tipo: 'imovel', teto: '', q: '' });
  const [lots, setLots] = useState<Lot[]>([]);
  const [facets, setFacets] = useState<Facets | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [scrapeLoading, setScrapeLoading] = useState(false);
  const [scrapeResult, setScrapeResult] = useState<ScrapeResult | null>(null);
  const [scrapeError, setScrapeError] = useState<string | null>(null);

  const tabs: Source[] = [{ id: '', label: 'Todas' }, ...sources];
  const cityOptions = useMemo(() => facets?.cidades ?? [], [facets]);

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
    params.set('limit', '80');
    Promise.all([
      fetch(`${API_URL}/api/lots?${params}`, { signal: ac.signal }),
      fetch(`${API_URL}/api/facets`, { signal: ac.signal }),
    ])
      .then(async ([lotsRes, facetsRes]) => {
        if (!lotsRes.ok) throw new Error('Falha ao carregar lotes');
        setLots(await lotsRes.json());
        setFacets(facetsRes.ok ? await facetsRes.json() : null);
        setError(null);
      })
      .catch((e) => {
        if (e instanceof Error && e.name === 'AbortError') return;
        const msg = e instanceof Error ? e.message : 'Falha ao carregar';
        setError(msg === 'Failed to fetch' ? 'Não foi possível conectar à API em 127.0.0.1:8050.' : msg);
        setLots([]);
      })
      .finally(() => {
        if (!ac.signal.aborted) setLoading(false);
      });
    return () => ac.abort();
  }, [source, applied, reloadToken]);

  const onSearch = (e: FormEvent) => {
    e.preventDefault();
    setApplied({ cidade: cidade.trim(), tipo, teto: teto.trim(), q: q.trim() });
  };

  const runScrape = async () => {
    setScrapeLoading(true);
    setScrapeResult(null);
    setScrapeError(null);
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 180_000);
    try {
      const res = await fetch(`${API_URL}/api/run-scrape`, { method: 'POST', signal: controller.signal });
      clearTimeout(timeoutId);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Falha ao rodar scrape');
      setScrapeResult(data);
      setReloadToken((n) => n + 1);
    } catch (e) {
      clearTimeout(timeoutId);
      if (e instanceof Error) {
        if (e.name === 'AbortError') setScrapeError('Scrape demorou mais de 3 minutos. Tente de novo.');
        else if (e.message === 'Failed to fetch') {
          setScrapeError('API fora. Suba o backend em 127.0.0.1:8050.');
        } else setScrapeError(e.message);
      } else setScrapeError('Erro ao rodar scrape');
    } finally {
      setScrapeLoading(false);
    }
  };

  const sourceCounts = Object.entries(facets?.by_source ?? {});

  return (
    <div aria-busy={loading}>
      <section className="kpis" aria-label="Resumo do catálogo">
        {sourceCounts.map(([name, count]) => (
          <div className="kpi" key={name}>
            <span>{name}</span>
            <strong>{count}</strong>
          </div>
        ))}
        <div className="kpi">
          <span>Com cidade</span>
          <strong>{facets ? `${facets.with_cidade}/${facets.total_lots}` : '—'}</strong>
        </div>
        <div className="kpi">
          <span>Extração</span>
          <strong>
            {facets?.extract?.gliner ? 'GLiNER' : 'regex'}
            {facets?.extract?.openrouter ? ' + Mistral' : ''}
          </strong>
        </div>
      </section>

      <div className="tabs" role="group" aria-label="Base de leilão">
        {tabs.map((tab) => (
          <button
            key={tab.id || 'all'}
            type="button"
            className="tab"
            aria-selected={source === tab.id}
            onClick={() => setSource(tab.id)}
          >
            {tab.label}
            {tab.id && facets?.by_source?.[tab.id] != null ? ` (${facets.by_source[tab.id]})` : ''}
          </button>
        ))}
      </div>

      <form className="toolbar" onSubmit={onSearch}>
        <label className="field">
          Busca
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="rua, bairro, matrícula…" />
        </label>
        <label className="field">
          Cidade
          <input
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
        </label>
        <label className="field">
          Tipo
          <select value={tipo} onChange={(e) => setTipo(e.target.value)}>
            <option value="">Todos</option>
            <option value="imovel">Imóvel (casa/apto/terreno)</option>
            <option value="casa">Casa</option>
            <option value="apartamento">Apartamento</option>
            <option value="terreno">Terreno</option>
            <option value="galpao">Galpão</option>
            <option value="chacara">Chácara</option>
            <option value="sala">Sala comercial</option>
            <option value="veiculo">Veículo</option>
          </select>
        </label>
        <label className="field">
          Teto (R$)
          <input value={teto} onChange={(e) => setTeto(e.target.value)} inputMode="numeric" placeholder="300000" />
        </label>
        <button className="btn" type="submit">
          Buscar
        </button>
        <button className="btn btn-secondary" type="button" onClick={runScrape} disabled={scrapeLoading} aria-busy={scrapeLoading}>
          {scrapeLoading ? 'Atualizando catálogo…' : 'Atualizar catálogo'}
        </button>
      </form>

      {scrapeError && <p className="msg msg-error">{scrapeError}</p>}
      {scrapeResult && (
        <p className="msg msg-ok">
          Catálogo atualizado: <strong>{scrapeResult.total_lots}</strong> lote(s)
          {scrapeResult.by_source &&
            Object.entries(scrapeResult.by_source).map(([name, v]) => (
              <span key={name}>
                {' '}
                · {name}: {v.lots}
              </span>
            ))}
          {scrapeResult.errors && scrapeResult.errors.length > 0 && (
            <span> · falha: {scrapeResult.errors.map((e) => e.source).join(', ')}</span>
          )}
        </p>
      )}

      {error && <p className="msg msg-error">{error}</p>}

      {loading && (
        <div>
          <p className="sr-only" aria-live="polite">
            Carregando lotes
          </p>
          <div className="lot-grid">
            <div className="lot-card skel" />
            <div className="lot-card skel" />
            <div className="lot-card skel" />
            <div className="lot-card skel" />
            <div className="lot-card skel" />
            <div className="lot-card skel" />
          </div>
        </div>
      )}

      {!loading && !error && lots.length === 0 && (
        <p className="meta">
          Nenhum lote com esses filtros. Clique em <strong>Atualizar catálogo</strong> para puxar Calil
          (calilleiloes.com.br), Vegas, Zuk, Mega e Grupo Lance, ou limpe cidade/tipo.
        </p>
      )}

      {!loading && !error && lots.length > 0 && (
        <div className="lot-grid">
          {lots.map((lot) => (
            <LotCard key={lot.id} lot={lot} />
          ))}
        </div>
      )}
    </div>
  );
}
