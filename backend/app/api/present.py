"""Monta DTOs da API a partir dos modelos persistidos."""
from __future__ import annotations

from app.api.schemas import LotOut
from app.models.schemas import LotModel
from app.search import cidade_of, endereco_of, foto_of, raw_dict, tipo_of
from app.scrapers.extract import format_card, tipo_from_text


def lot_to_out(lot: LotModel, source: str) -> LotOut:
    extra = format_card(
        getattr(lot, "title", None) or "",
        getattr(lot, "description", None),
        raw_dict(lot),
    )
    tipo = extra.get("tipo") or tipo_of(lot) or tipo_from_text(getattr(lot, "title", None), getattr(lot, "category", None))
    return LotOut(
        id=lot.id,
        auction_id=lot.auction_id,
        external_id=lot.external_id,
        source=source,
        title=lot.title,
        description=lot.description,
        category=lot.category,
        tipo=tipo,
        headline=extra.get("headline"),
        cidade=extra.get("cidade") or cidade_of(lot),
        bairro=extra.get("bairro"),
        endereco=extra.get("endereco") or endereco_of(lot),
        matricula=extra.get("matricula"),
        area=extra.get("area"),
        foto=foto_of(lot) or (extra.get("foto") if isinstance(extra.get("foto"), str) and extra["foto"].startswith("http") and "facebook.com/tr" not in extra["foto"] else None),
        valor_m2_regiao=extra.get("valor_m2_regiao"),
        valor_mercado_estimado=extra.get("valor_mercado_estimado"),
        minimum_bid=lot.minimum_bid,
        current_bid=lot.current_bid,
        reference_value=lot.reference_value,
        url=lot.url,
        updated_at=lot.updated_at,
    )
