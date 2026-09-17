'use client';

import Link from 'next/link';
import { FormEvent, useEffect, useState } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

type Source = { id: string; label: string };

type Lot = {
  id: number;
  auction_id: number;
  external_id: string;
  source: string;
  title: string;
  category: string | null;
  cidade: string | null;
  current_bid: number | null;
  minimum_bid: number | null;
  url: string | null;
};

type Stats = { total_auctions: number; total_lots: number } | null;

type ScrapeResult = {
  status: string;
  total_auctions: number;
  total_lots: number;
  by_source?: Record<string, { auctions: number; lots: number }>;
};

const DEMO: Source = { id: 'demo', label: 'Demo' };

function formatMoney(value: number | null): string {
  if (value == null) return '—';
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 }).format(value);
}

function httpUrl(url: string | null): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    if (parsed.protocol === 'http:' || parsed.protocol === 'https:') return url;
  } catch {
    return null;
  }
  return null;
}

export default function Home() {
  const [sources, setSources] = useState<Source[]>([DEMO]);
  const [source, setSource] = useState('');
  const [cidade, setCidade] = useState('');
  const [tipo, setTipo] = useState('');
  const [teto, setTeto] = useState('');
  const [applied, setApplied] = useState({ cidade: '', tipo: '', teto: '' });
  const [lots, setLots] = useState<Lot[]>([]);
  const [stats, setStats] = useState<Stats>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [scrapeLoading, setScrapeLoading] = useState(false);
  const [scrapeResult, setScrapeResult] = useState<ScrapeResult | null>(null);
  const [scrapeError, setScrapeError] = useState<string | null>(null);

  const tabs: Source[] = [{ id: '', label: 'Todas' }, ...sources.filter((s) => s.id !== 'demo'), DEMO];

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
    Promise.all([
      fetch(`${API_URL}/api/lots?${params}`, { signal: ac.signal }),
      fetch(`${API_URL}/api/stats`, { signal: ac.signal }),
    ])
      .then(async ([lotsRes, statsRes]) => {
        if (!lotsRes.ok) throw new Error('Falha ao carregar lotes');
        setLots(await lotsRes.json());
        setStats(statsRes.ok ? await statsRes.json() : null);
        setError(null);
      })
      .catch((e) => {
        if (e instanceof Error && e.name === 'AbortError') return;
        const msg = e instanceof Error ? e.message : 'Falha ao carregar';
        setError(msg === 'Failed to fetch' ? 'Não foi possível conectar ao backend. Verifique NEXT_PUBLIC_API_URL.' : msg);
        setLots([]);
      })
      .finally(() => {
        if (!ac.signal.aborted) setLoading(false);
      });
    return () => ac.abort();
  }, [source, applied, reloadToken]);

  const onSearch = (e: FormEvent) => {
    e.preventDefault();
    setApplied({ cidade: cidade.trim(), tipo, teto: teto.trim() });
  };

  const runScrape = async () => {
    setScrapeLoading(true);
    setScrapeResult(null);
    setScrapeError(null);
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 120_000);
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
        if (e.name === 'AbortError') setScrapeError('Scrape demorou mais de 2 minutos. Tente de novo.');
        else if (e.message === 'Failed to fetch') {
          setScrapeError('Não foi possível conectar ao backend. Verifique se NEXT_PUBLIC_API_URL é a URL pública da API.');
        } else setScrapeError(e.message);
      } else setScrapeError('Erro ao rodar scrape');
    } finally {
      setScrapeLoading(false);
    }
  };

  const emptyHint =
    source === 'demo'
      ? 'A base demo ainda não tem lotes persistidos. As outras bases entram pelo scrape.'
      : 'Nenhum lote nesta base com esses filtros. Rode o scrape ou altere cidade, tipo e teto.';

  return (
    <div aria-busy={loading}>
      <div className="tabs" role="group" aria-label="Base de leilão">
        {tabs.map((tab) => (
          <button
            key={tab.id || 'all'}
            type="button"
            className="tab"
            aria-pressed={source === tab.id}
            onClick={() => setSource(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <form className="toolbar" onSubmit={onSearch}>
        <label className="field">
          Cidade
          <input value={cidade} onChange={(e) => setCidade(e.target.value)} placeholder="Sertãozinho" />
        </label>
        <label className="field">
          Tipo
          <select value={tipo} onChange={(e) => setTipo(e.target.value)}>
            <option value="">Todos</option>
            <option value="casa">Casa</option>
            <option value="apartamento">Apartamento</option>
            <option value="terreno">Terreno</option>
            <option value="imovel">Imóvel</option>
          </select>
        </label>
        <label className="field">
          Teto (R$)
          <input value={teto} onChange={(e) => setTeto(e.target.value)} inputMode="numeric" placeholder="300000" />
        </label>
        <button className="btn" type="submit">
          Buscar
        </button>
        <button className="btn" type="button" onClick={runScrape} disabled={scrapeLoading} aria-busy={scrapeLoading}>
          {scrapeLoading ? 'Rodando scrape…' : 'Rodar scrape'}
        </button>
      </form>

      {scrapeError && <p className="msg msg-error">{scrapeError}</p>}
      {scrapeResult && (
        <p className="msg msg-ok">
          Scrape concluído: <strong>{scrapeResult.total_auctions}</strong> leilão(ões),{' '}
          <strong>{scrapeResult.total_lots}</strong> lote(s)
          {scrapeResult.by_source &&
            Object.entries(scrapeResult.by_source).map(([name, v]) => (
              <span key={name}>
                {' '}
                · {name}: {v.lots} lote(s)
              </span>
            ))}
        </p>
      )}

      {error && <p className="msg msg-error">{error}</p>}
      {!loading && stats && (
        <p className="meta">
          <strong>{stats.total_lots}</strong> lote(s) no banco · <strong>{stats.total_auctions}</strong> leilão(ões)
        </p>
      )}

      {loading && (
        <div>
          <p className="sr-only" aria-live="polite">
            Carregando lotes
          </p>
          <ul className="list">
            <li className="card skel" />
            <li className="card skel" />
            <li className="card skel" />
            <li className="card skel" />
          </ul>
        </div>
      )}

      {!loading && !error && lots.length === 0 && <p className="meta">{emptyHint}</p>}

      {!loading && !error && lots.length > 0 && (
        <ul className="list">
          {lots.map((lot) => {
            const site = httpUrl(lot.url);
            return (
              <li key={lot.id} className="card">
                <div className="card-head">
                  <div>
                    <span className="source-tag">{lot.source}</span>
                    <strong>{lot.title}</strong>
                  </div>
                  <span>{formatMoney(lot.current_bid ?? lot.minimum_bid)}</span>
                </div>
                <div className="card-meta">
                  {lot.cidade && <span>{lot.cidade}</span>}
                  {lot.category && <span>{lot.category}</span>}
                  <Link href={`/leilao/${lot.auction_id}`}>Ver leilão →</Link>
                  {site && (
                    <a href={site} target="_blank" rel="noopener noreferrer">
                      Ver no site
                    </a>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
