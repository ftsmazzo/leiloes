"""
Grava leilões e lotes. Re-scrape atualiza lance/título; não duplica.
"""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.schemas import AuctionModel, LotModel
from app.scrapers.base import ScrapedAuction, ScrapedLot
from app.scrapers.extract import extra_json
from app.scoring import compute_score


KEEP_RAW_KEYS = (
    "alertado",
    "parecer",
    "docs",
    "avaliado_em",
    "ocupacao",
    "dividas",
    "avaliacao_edital",
    "avaliacao_fonte",
    "valor_venal_imovel",
    "valor_venal_terreno",
    "avaliacao_data",
    "avaliacao_data_origem",
    "edital_sem_texto",
    "docs_limitados",
    "lance_pagina",
    "avaliacao_pagina",
    "riscos",
    "processo_cnj",
    "nao_entrar",
)


def _merge_raw_data(existing_raw: str | None, new_raw: str) -> str:
    """raw_data é recalculado do zero a cada scrape — preserva alerta e
    avaliação sob demanda (#solicitar-avaliacao), senão o re-scrape apagaria
    o parecer e reenviaria Telegram."""
    if not existing_raw:
        return new_raw
    try:
        old = json.loads(existing_raw)
        new = json.loads(new_raw)
    except json.JSONDecodeError:
        return new_raw
    if not (isinstance(old, dict) and isinstance(new, dict)):
        return new_raw
    for key in KEEP_RAW_KEYS:
        if old.get(key) not in (None, "", [], {}) and key not in new:
            new[key] = old[key]
    if old.get("avaliado_em") and "avaliado_em" not in new:
        new["avaliado_em"] = old["avaliado_em"]
    return json.dumps(new, ensure_ascii=False)


def _refresh_score_if_avaliado(lot: LotModel) -> None:
    """Lote já avaliado: recorre o score com o lance novo e os dados do edital."""
    if not lot.raw_data:
        return
    try:
        extra = json.loads(lot.raw_data)
    except json.JSONDecodeError:
        return
    if not isinstance(extra, dict) or not extra.get("avaliado_em"):
        return
    ref = extra.get("avaliacao_edital")
    if not isinstance(ref, (int, float)):
        ref = lot.reference_value
    ocupacao = extra.get("ocupacao") if extra.get("ocupacao") in ("ocupado", "desocupado") else None
    tem_divida = True if extra.get("dividas") else None
    mercado = extra.get("valor_mercado_estimado")
    fonte = extra.get("avaliacao_fonte") if extra.get("avaliacao_fonte") in ("laudo", "venal_imovel") else None
    info = compute_score(
        title=lot.title,
        description=lot.description,
        current_bid=lot.current_bid,
        minimum_bid=lot.minimum_bid,
        reference_value=ref if isinstance(ref, (int, float)) else None,
        valor_mercado_estimado=mercado if isinstance(mercado, (int, float)) else None,
        ocupacao=ocupacao,
        tem_divida=tem_divida,
        fonte_avaliacao=fonte,
        dividas=extra.get("dividas") if isinstance(extra.get("dividas"), dict) else None,
        avaliacao_data=extra.get("avaliacao_data"),
        avaliacao_data_origem=extra.get("avaliacao_data_origem")
        if extra.get("avaliacao_data_origem") in ("laudo", "processo")
        else None,
        tipo=extra.get("tipo") if isinstance(extra.get("tipo"), str) else None,
        riscos=extra.get("riscos") if isinstance(extra.get("riscos"), dict) else None,
    )
    extra["score"] = info["score"]
    extra["score_tem_comparacao_preco"] = info["tem_comparacao_preco"]
    extra["score_motivos"] = info["motivos"]
    lot.raw_data = extra_json(extra)


def apply_lot(lot: LotModel, sl: ScrapedLot) -> None:
    lot.title = sl.title
    if sl.description is not None:
        lot.description = sl.description
    if sl.category is not None:
        lot.category = sl.category
    if sl.url is not None:
        lot.url = sl.url
    if sl.raw_data is not None:
        lot.raw_data = _merge_raw_data(lot.raw_data, sl.raw_data)
    if sl.minimum_bid is not None:
        lot.minimum_bid = sl.minimum_bid
    if sl.current_bid is not None:
        lot.current_bid = sl.current_bid
    if sl.reference_value is not None:
        lot.reference_value = sl.reference_value
    _refresh_score_if_avaliado(lot)
    lot.updated_at = datetime.utcnow()


def persist_auctions(session: Session, auctions: list[ScrapedAuction]) -> list[tuple[LotModel, str]]:
    touched: list[tuple[LotModel, str]] = []
    for sa in auctions:
        auction_id = _upsert_auction(session, sa)
        for sl in sa.lots:
            lot = _upsert_lot(session, auction_id, sl)
            touched.append((lot, sa.source))
    return touched


def _upsert_auction(session: Session, sa: ScrapedAuction) -> int:
    existing = session.execute(
        select(AuctionModel).where(
            AuctionModel.source == sa.source,
            AuctionModel.external_id == sa.external_id,
        )
    ).scalar_one_or_none()
    if existing is None:
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
        session.flush()
        return auction.id
    existing.title = sa.title
    if sa.url is not None:
        existing.url = sa.url
    if sa.description is not None:
        existing.description = sa.description
    if sa.starts_at is not None:
        existing.starts_at = sa.starts_at
    if sa.ends_at is not None:
        existing.ends_at = sa.ends_at
    existing.updated_at = datetime.utcnow()
    session.flush()
    return existing.id


def _upsert_lot(session: Session, auction_id: int, sl: ScrapedLot) -> LotModel:
    existing = session.execute(
        select(LotModel).where(
            LotModel.auction_id == auction_id,
            LotModel.external_id == sl.external_id,
        )
    ).scalar_one_or_none()
    if existing is None:
        lot = LotModel(
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
        session.add(lot)
        session.flush()
        return lot
    apply_lot(existing, sl)
    return existing
