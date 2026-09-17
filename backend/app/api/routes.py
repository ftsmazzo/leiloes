from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.models.schemas import AuctionModel, LotModel
from app.api.schemas import AuctionOut, AuctionDetailOut, LotOut
from app.api.present import lot_to_out
from app.search import filter_lots
from app.scrapers.registry import source_names

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/auctions", response_model=list[AuctionOut])
async def list_auctions(
    source: Optional[str] = Query(None, description="Filtrar por fonte: calil, vegas, zuk, mega, lance"),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    q = select(AuctionModel).order_by(AuctionModel.updated_at.desc()).limit(limit).offset(offset)
    if source:
        q = q.where(AuctionModel.source == source)
    result = await db.execute(q)
    auctions = result.scalars().all()
    out = []
    for a in auctions:
        count = await db.execute(select(func.count(LotModel.id)).where(LotModel.auction_id == a.id))
        lots_count = count.scalar() or 0
        out.append(AuctionOut(
            id=a.id,
            external_id=a.external_id,
            source=a.source,
            title=a.title,
            url=a.url,
            description=a.description,
            starts_at=a.starts_at,
            ends_at=a.ends_at,
            lots_count=lots_count,
            updated_at=a.updated_at,
        ))
    return out


@router.get("/auctions/{auction_id}", response_model=AuctionDetailOut)
async def get_auction(auction_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AuctionModel).where(AuctionModel.id == auction_id))
    auction = result.scalar_one_or_none()
    if not auction:
        from fastapi import HTTPException
        raise HTTPException(404, "Leilão não encontrado")
    lots_result = await db.execute(select(LotModel).where(LotModel.auction_id == auction_id).order_by(LotModel.id))
    lots = lots_result.scalars().all()
    return AuctionDetailOut(
        id=auction.id,
        external_id=auction.external_id,
        source=auction.source,
        title=auction.title,
        url=auction.url,
        description=auction.description,
        starts_at=auction.starts_at,
        ends_at=auction.ends_at,
        lots_count=len(lots),
        updated_at=auction.updated_at,
        lots=[lot_to_out(lot, auction.source) for lot in lots],
    )


@router.get("/lots", response_model=list[LotOut])
async def list_lots(
    auction_id: Optional[int] = Query(None),
    source: Optional[str] = Query(None),
    cidade: Optional[str] = Query(None, description="Cidade gravada pelo scraper (raw_data/título)"),
    tipo: Optional[str] = Query(None, description="Casa, terreno, imóvel — casa com category/título"),
    teto: Optional[float] = Query(None, ge=0, description="Lance atual ou mínimo até este valor"),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    cidade = cidade.strip() if cidade else None
    tipo = tipo.strip() if tipo else None
    q = (
        select(LotModel, AuctionModel.source)
        .join(AuctionModel, LotModel.auction_id == AuctionModel.id)
        .order_by(LotModel.updated_at.desc())
    )
    if auction_id:
        q = q.where(LotModel.auction_id == auction_id)
    if source:
        q = q.where(AuctionModel.source == source)
    if teto is not None:
        q = q.where(
            or_(
                LotModel.current_bid <= teto,
                and_(LotModel.current_bid.is_(None), LotModel.minimum_bid <= teto),
            )
        )
    text_filter = bool(cidade or tipo)
    if not text_filter:
        q = q.limit(limit).offset(offset)
    result = await db.execute(q)
    rows = list(result.all())
    if text_filter:
        lots_only = [row[0] for row in rows]
        kept_ids = {lot.id for lot in filter_lots(lots_only, cidade=cidade, tipo=tipo)}
        rows = [row for row in rows if row[0].id in kept_ids]
        rows = rows[offset : offset + limit]
    return [lot_to_out(lot, src) for lot, src in rows]


@router.get("/sources")
async def list_sources():
    labels = {"calil": "Calil", "vegas": "Vegas", "zuk": "Zuk", "mega": "Mega", "lance": "Grupo Lance", "demo": "Demo"}
    return [{"id": name, "label": labels.get(name, name.title())} for name in source_names()]


@router.get("/stats")
async def stats(db: AsyncSession = Depends(get_db)):
    """Total de leilões e lotes para o dashboard."""
    r_auctions = await db.execute(select(func.count(AuctionModel.id)))
    r_lots = await db.execute(select(func.count(LotModel.id)))
    return {
        "total_auctions": r_auctions.scalar() or 0,
        "total_lots": r_lots.scalar() or 0,
    }


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/run-scrape")
async def run_scrape():
    """
    Dispara a execução de todos os scrapers registrados e persiste no banco.
    Use para validar o primeiro scrape ou atualizar dados manualmente.
    Pode demorar alguns segundos.
    """
    from app.scrapers.run_all import run_all
    summary = await run_all()
    return {"status": "ok", **summary}
