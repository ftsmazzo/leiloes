"""
Executa todos os scrapers e persiste no banco.
Uso: python -m app.scrapers.run_all
Ou: POST /api/run-scrape (pela API).
"""
import asyncio
import os
import sys

# Garantir que o app está no path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.models.database import Base, engine, AsyncSessionLocal
from app.scrapers.persist import persist_auctions
from app.scrapers.registry import all_scrapers
from app.scrapers.extract import enrich_extra, extra_json
import json


def _enrich_auctions(auctions, cap: int = 12) -> None:
    used = 0
    for auction in auctions:
        for lot in auction.lots:
            extra = {}
            if lot.raw_data:
                try:
                    parsed = json.loads(lot.raw_data)
                    if isinstance(parsed, dict):
                        extra = parsed
                except json.JSONDecodeError:
                    extra = {}
            filled = enrich_extra(lot.title, lot.description, extra, use_ai=used < cap)
            if filled.get("extract") in ("gliner", "mistral"):
                used += 1
            lot.raw_data = extra_json(filled)
            if filled.get("tipo") and not lot.category:
                lot.category = str(filled["tipo"])


async def run_all(on_progress=None):
    """Retorna dict com total_auctions, total_lots, by_source e errors.

    on_progress(source_name, summary_parcial), se passado, e chamado apos cada
    scraper terminar (ok ou com erro) — usado pra reportar progresso numa
    rodada assincrona (ver POST /api/run-scrape).
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    scrapers = all_scrapers()
    summary = {"total_auctions": 0, "total_lots": 0, "by_source": {}, "errors": []}

    async with AsyncSessionLocal() as session:
        for scraper in scrapers:
            try:
                print(f"Executando scraper: {scraper.source_name}...")
                auctions = await scraper.scrape()
                n_auctions, n_lots = len(auctions), sum(len(a.lots) for a in auctions)
                print(f"  -> {n_auctions} leilão(ões), {n_lots} lote(s)")
                _enrich_auctions(auctions)
                summary["by_source"][scraper.source_name] = {"auctions": n_auctions, "lots": n_lots}
                summary["total_auctions"] += n_auctions
                summary["total_lots"] += n_lots
                await session.run_sync(persist_auctions, auctions)
                await session.commit()
            except Exception as e:
                await session.rollback()
                print(f"Erro no scraper {scraper.source_name}: {e}")
                summary["errors"].append({"source": scraper.source_name, "error": str(e)})
            if on_progress is not None:
                on_progress(scraper.source_name, summary)
            await asyncio.sleep(1)  # Respeito entre fontes
    print("Scrapers concluídos.")
    return summary


if __name__ == "__main__":
    asyncio.run(run_all())
