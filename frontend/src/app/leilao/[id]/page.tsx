'use client';

import { useParams, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

type Lot = {
  id: number;
  external_id: string;
  title: string;
  category: string | null;
  cidade: string | null;
  minimum_bid: number | null;
  current_bid: number | null;
  reference_value: number | null;
  url: string | null;
};

type AuctionDetail = {
  id: number;
  source: string;
  title: string;
  url: string | null;
  description: string | null;
  lots_count: number;
  updated_at: string;
  lots: Lot[];
};

function formatMoney(value: number | null): string {
  if (value == null) return '—';
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 }).format(
    value,
  );
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

export default function LeilaoDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params?.id as string;
  const [data, setData] = useState<AuctionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    const ac = new AbortController();
    setLoading(true);
    setData(null);
    setError(null);
    fetch(`${API_URL}/api/auctions/${id}`, { signal: ac.signal })
      .then((res) => {
        if (!res.ok) throw new Error('Leilão não encontrado');
        return res.json();
      })
      .then(setData)
      .catch((e) => {
        if (e instanceof Error && e.name === 'AbortError') return;
        setError(e instanceof Error ? e.message : 'Falha ao carregar');
      })
      .finally(() => {
        if (!ac.signal.aborted) setLoading(false);
      });
    return () => ac.abort();
  }, [id]);

  const site = httpUrl(data?.url ?? null);

  if (loading) {
    return (
      <div aria-busy="true">
        <p className="sr-only" aria-live="polite">
          Carregando leilão
        </p>
        <div className="card skel" style={{ marginBottom: '1rem' }} />
        <ul className="list">
          <li className="card skel" />
          <li className="card skel" />
        </ul>
      </div>
    );
  }
  if (error) return <p className="msg msg-error">{error}</p>;
  if (!data) return null;

  return (
    <div>
      <p style={{ marginBottom: '1rem' }}>
        <button type="button" className="btn-ghost" onClick={() => router.back()}>
          ← Voltar
        </button>
      </p>
      <header style={{ marginBottom: '1.5rem', paddingBottom: '1rem', borderBottom: '1px solid var(--line)' }}>
        <span className="source-tag">{data.source}</span>
        <h1 style={{ margin: '0.25rem 0', fontSize: '1.5rem' }}>{data.title}</h1>
        {data.description && <p className="meta">{data.description}</p>}
        <p className="meta">
          {data.lots_count} lote(s) · Atualizado: {new Date(data.updated_at).toLocaleString('pt-BR')}
        </p>
        {site && (
          <a href={site} target="_blank" rel="noopener noreferrer">
            Ver no site original →
          </a>
        )}
      </header>
      <h2 style={{ fontSize: '1.1rem', marginBottom: '0.75rem' }}>Lotes</h2>
      <ul className="list">
        {data.lots.map((lot) => {
          const lotSite = httpUrl(lot.url);
          return (
            <li key={lot.id} className="card">
              <div className="card-head">
                <strong>{lot.title}</strong>
                <span>{formatMoney(lot.current_bid ?? lot.minimum_bid)}</span>
              </div>
              <div className="card-meta">
                {lot.cidade && <span>{lot.cidade}</span>}
                {lot.category && <span>{lot.category}</span>}
                {lot.reference_value != null && <span>Avaliação: {formatMoney(lot.reference_value)}</span>}
                {lotSite && (
                  <a href={lotSite} target="_blank" rel="noopener noreferrer">
                    Ver no site →
                  </a>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
