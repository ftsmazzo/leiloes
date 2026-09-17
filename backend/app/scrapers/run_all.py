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

from sqlalchemy import select

from app.models.database import Base, engine, AsyncSessionLocal
from app.models.schemas import AuctionModel, LotModel
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
                for sa in auctions:
                    result = await session.execute(
                        select(AuctionModel).where(
                            AuctionModel.source == sa.source,
                            AuctionModel.external_id == sa.external_id,
                        )
                    )
                    existing = result.scalar_one_or_none()
                    if existing:
                        existing.title = sa.title
                        existing.url = sa.url
                        existing.description = sa.description
                        existing.starts_at = sa.starts_at
                        existing.ends_at = sa.ends_at
                        session.add(existing)
                        auction_id = existing.id
                    else:
                        auction = AuctionModel(
                            external_id=sa.external_id,
                            source=sa.source,
                            title=sa.title,
                            url=sa.url,
                            description=sa.description,
                            starts_at=sa.starts_at,
                            ends_at=sa.ends_at,
                        )
                        session.add(auction)
                        await session.flush()
                        auction_id = auction.id

                    for sl in sa.lots:
                        lot_result = await session.execute(
                            select(LotModel).where(
                                LotModel.auction_id == auction_id,
                                LotModel.external_id == sl.external_id,
                            )
                        )
                        if lot_result.scalar_one_or_none() is None:
                            session.add(
                                LotModel(
                                    auction_id=auction_id,
                                    external_id=sl.external_id,
                                    title=sl.title,
                                    description=sl.description,
                                    category=sl.category,
                                    minimum_bid=sl.minimum_bid,
                                    current_bid=sl.current_bid,
                                    reference_value=sl.reference_value,
                                    url=sl.url,
                                    raw_data=sl.raw_data,
                                )
                            )
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
