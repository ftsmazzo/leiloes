from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class LotOut(BaseModel):
    id: int
    auction_id: int
    external_id: str
    source: str
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    tipo: Optional[str] = None
    headline: Optional[str] = None
    cidade: Optional[str] = None
    bairro: Optional[str] = None
    endereco: Optional[str] = None
    matricula: Optional[str] = None
    area: Optional[str] = None
    foto: Optional[str] = None
    valor_m2_regiao: Optional[float] = None
    valor_mercado_estimado: Optional[float] = None
    minimum_bid: Optional[float] = None
    current_bid: Optional[float] = None
    reference_value: Optional[float] = None
    url: Optional[str] = None
    updated_at: datetime

    class Config:
        from_attributes = False


class AuctionOut(BaseModel):
    id: int
    external_id: str
    source: str
    title: str
    url: Optional[str] = None
    description: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    lots_count: int = 0
    updated_at: datetime

    class Config:
        from_attributes = True


class AuctionDetailOut(AuctionOut):
    lots: list[LotOut] = []
