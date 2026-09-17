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


def _merge_raw_data(existing_raw: str | None, new_raw: str) -> str:
    """raw_data é recalculado do zero a cada scrape — preserva o flag
    "alertado" do registro antigo, senão o alerta de oportunidade (#34)
    reenviaria a cada rodada pro mesmo lote."""
    if not existing_raw:
        return new_raw
    try:
        old = json.loads(existing_raw)
        new = json.loads(new_raw)
    except json.JSONDecodeError:
        return new_raw
    if isinstance(old, dict) and isinstance(new, dict) and old.get("alertado"):
        new["alertado"] = True
        return json.dumps(new, ensure_ascii=False)
    return new_raw


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
