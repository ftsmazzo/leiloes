"""Monta DTOs da API a partir dos modelos persistidos."""
from __future__ import annotations

from app.api.schemas import LotOut
from app.models.schemas import LotModel
from app.search import cidade_of


def lot_to_out(lot: LotModel, source: str) -> LotOut:
    return LotOut(
        id=lot.id,
        auction_id=lot.auction_id,
        external_id=lot.external_id,
        source=source,
        title=lot.title,
        description=lot.description,
        category=lot.category,
        cidade=cidade_of(lot),
        minimum_bid=lot.minimum_bid,
        current_bid=lot.current_bid,
        reference_value=lot.reference_value,
        url=lot.url,
        updated_at=lot.updated_at,
    )
