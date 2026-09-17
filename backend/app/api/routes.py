import time
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_db
from app.models.schemas import AuctionModel, LotModel
from app.api.schemas import AuctionOut, AuctionDetailOut, LotOut
from app.api.present import lot_to_out
from app.search import cidade_of, filter_lots, score_sort_key, tipo_of
from app.scrapers.registry import source_names
from app.scrapers.extract import extract_status
from app.alerts import alert_status

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
    else:
        q = q.where(AuctionModel.source != "demo")
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
    tipo: Optional[str] = Query(None, description="casa, apartamento, terreno, imovel…"),
    teto: Optional[float] = Query(None, ge=0, description="Lance atual ou mínimo até este valor"),
    q: Optional[str] = Query(None, description="Texto livre em título, endereço e cidade"),
    sort: Optional[str] = Query(None, description="score = ordenar por score de oportunidade (desc)"),
    limit: int = Query(80, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    cidade = cidade.strip() if cidade else None
    tipo = tipo.strip() if tipo else None
    q_txt = q.strip() if q else None
    by_score = sort == "score"
    stmt = (
        select(LotModel, AuctionModel.source)
        .join(AuctionModel, LotModel.auction_id == AuctionModel.id)
        .order_by(LotModel.updated_at.desc())
    )
    if auction_id:
        stmt = stmt.where(LotModel.auction_id == auction_id)
    if source:
        stmt = stmt.where(AuctionModel.source == source)
    else:
        stmt = stmt.where(AuctionModel.source != "demo")
    if teto is not None:
        stmt = stmt.where(
            or_(
                LotModel.current_bid <= teto,
                and_(LotModel.current_bid.is_(None), LotModel.minimum_bid <= teto),
            )
        )
    text_filter = bool(cidade or tipo or q_txt)
    python_pass = text_filter or by_score
    if not python_pass:
        stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    rows = list(result.all())
    if text_filter:
        lots_only = [row[0] for row in rows]
        kept_ids = {lot.id for lot in filter_lots(lots_only, cidade=cidade, tipo=tipo, q=q_txt)}
        rows = [row for row in rows if row[0].id in kept_ids]
    if by_score:
        # score fica em raw_data (não é coluna) — não dá pra ordenar em SQL
        rows = sorted(rows, key=lambda row: score_sort_key(row[0]))
    if python_pass:
        rows = rows[offset : offset + limit]
    return [lot_to_out(lot, src) for lot, src in rows]


@router.get("/facets")
async def facets(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(LotModel, AuctionModel.source)
        .join(AuctionModel, LotModel.auction_id == AuctionModel.id)
        .where(AuctionModel.source != "demo")
    )
    rows = list(result.all())
    cidades: dict[str, int] = {}
    tipos: dict[str, int] = {}
    by_source: dict[str, int] = {}
    with_city = 0
    for lot, src in rows:
        by_source[src] = by_source.get(src, 0) + 1
        cidade = cidade_of(lot)
        if cidade:
            with_city += 1
            cidades[cidade] = cidades.get(cidade, 0) + 1
        tipo = tipo_of(lot)
        if not tipo:
            continue
        tipos[tipo] = tipos.get(tipo, 0) + 1
    return {
        "total_lots": len(rows),
        "with_cidade": with_city,
        "by_source": by_source,
        "cidades": sorted(cidades.items(), key=lambda kv: (-kv[1], kv[0])),
        "tipos": sorted(tipos.items(), key=lambda kv: (-kv[1], kv[0])),
        "extract": extract_status(),
        "alerts": alert_status(),
    }


@router.get("/sources")
async def list_sources():
    labels = {
        "calil": "Calil",
        "vegas": "Vegas",
        "zuk": "Zuk",
        "mega": "Mega",
        "lance": "Grupo Lance",
        "demo": "Demo",
    }
    return [{"id": name, "label": labels.get(name, name.title())} for name in source_names()]


@router.get("/stats")
async def stats(db: AsyncSession = Depends(get_db)):
    r_auctions = await db.execute(select(func.count(AuctionModel.id)).where(AuctionModel.source != "demo"))
    r_lots = await db.execute(
        select(func.count(LotModel.id))
        .join(AuctionModel, LotModel.auction_id == AuctionModel.id)
        .where(AuctionModel.source != "demo")
    )
    return {
        "total_auctions": r_auctions.scalar() or 0,
        "total_lots": r_lots.scalar() or 0,
        "extract": extract_status(),
        "alerts": alert_status(),
    }


@router.get("/health")
async def health():
    return {"status": "ok", "extract": extract_status(), "alerts": alert_status()}


RUN_SCRAPE_COOLDOWN_S = 60.0
_scrape_running = False
_scrape_last_finished: float | None = None
_scrape_job: dict = {
    "status": "idle",  # idle | running | done | error
    "summary": None,
    "error": None,
    "current_source": None,
    "started_at": None,
    "finished_at": None,
}


async def _run_scrape_job() -> None:
    """Roda em segundo plano (BackgroundTasks) — não bloqueia a resposta do POST."""
    global _scrape_running, _scrape_last_finished
    from app.scrapers.run_all import run_all

    def on_progress(source_name: str, partial_summary: dict) -> None:
        # run_all reusa e muta o mesmo dict a cada fonte — snapshot próprio
        # pra status não "vazar" a fonte seguinte antes do current_source virar.
        _scrape_job["summary"] = {
            **partial_summary,
            "by_source": dict(partial_summary.get("by_source") or {}),
            "errors": list(partial_summary.get("errors") or []),
        }
        _scrape_job["current_source"] = source_name

    try:
        summary = await run_all(on_progress=on_progress)
        _scrape_job["summary"] = summary
        _scrape_job["status"] = "done"
    except Exception as exc:
        _scrape_job["status"] = "error"
        _scrape_job["error"] = str(exc)
    finally:
        _scrape_job["current_source"] = None
        _scrape_job["finished_at"] = time.time()
        _scrape_running = False
        _scrape_last_finished = time.monotonic()


@router.post("/run-scrape", status_code=202)
async def run_scrape(background_tasks: BackgroundTasks):
    """
    Dispara em segundo plano a execução de todos os scrapers registrados
    (Calil, Vegas, Zuk, Mega, Grupo Lance) e persiste no banco. Retorna
    imediatamente (202) sem esperar o scrape terminar — acompanhe o
    progresso em GET /api/run-scrape/status. Limitado a uma execução por
    vez, com intervalo mínimo entre rodadas, pois cada chamada bate nos
    sites de origem.
    """
    global _scrape_running
    if _scrape_running:
        raise HTTPException(status_code=429, detail="Já existe um scrape em andamento. Aguarde terminar.")
    if _scrape_last_finished is not None:
        elapsed = time.monotonic() - _scrape_last_finished
        if elapsed < RUN_SCRAPE_COOLDOWN_S:
            retry_after = int(RUN_SCRAPE_COOLDOWN_S - elapsed) + 1
            raise HTTPException(
                status_code=429,
                detail=f"Aguarde {retry_after}s antes de rodar o scrape de novo.",
                headers={"Retry-After": str(retry_after)},
            )
    _scrape_running = True
    _scrape_job.update(
        status="running",
        summary=None,
        error=None,
        current_source=None,
        started_at=time.time(),
        finished_at=None,
    )
    background_tasks.add_task(_run_scrape_job)
    return {"status": "started"}


@router.get("/run-scrape/status")
async def run_scrape_status():
    return dict(_scrape_job)
