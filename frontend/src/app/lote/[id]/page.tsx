'use client';

import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import { Lot } from '../../../components/LotCard';
import { LotDossier } from '../../../components/LotDossier';
import { API_URL } from '../../../lib/api';

export default function LoteAnalisePage() {
  const params = useParams();
  const id = params?.id as string;
  const [lot, setLot] = useState<Lot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    const ac = new AbortController();
    setLoading(true);
    setError(null);
    fetch(`${API_URL}/api/lots/${id}`, { signal: ac.signal })
      .then((res) => {
        if (!res.ok) throw new Error(res.status === 404 ? 'Lote não encontrado' : 'Falha ao carregar');
        return res.json();
      })
      .then((data: Lot) => setLot(data))
      .catch((e) => {
        if (e instanceof Error && e.name === 'AbortError') return;
        setError(e instanceof Error ? e.message : 'Falha ao carregar');
      })
      .finally(() => {
        if (!ac.signal.aborted) setLoading(false);
      });
    return () => ac.abort();
  }, [id]);

  if (loading) {
    return (
      <div className="dossier" aria-busy="true">
        <p className="sr-only" aria-live="polite">
          Carregando análise
        </p>
        <div className="dossier-skel" />
      </div>
    );
  }
  if (error) return <p className="msg msg-error">{error}</p>;
  if (!lot) return null;
  return <LotDossier lot={lot} />;
}
