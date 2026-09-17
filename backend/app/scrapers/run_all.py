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


async def run_all():
    """Retorna dict com total_auctions, total_lots, by_source e errors."""
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
                summary["by_source"][scraper.source_name] = {"auctions": n_auctions, "lots": n_lots}
                summary["total_auctions"] += n_auctions
                summary["total_lots"] += n_lots
                await session.run_sync(persist_auctions, auctions)
                await session.commit()
            except Exception as e:
                await session.rollback()
                print(f"Erro no scraper {scraper.source_name}: {e}")
                summary["errors"].append({"source": scraper.source_name, "error": str(e)})
            await asyncio.sleep(1)  # Respeito entre fontes
    print("Scrapers concluídos.")
    return summary


if __name__ == "__main__":
    asyncio.run(run_all())
