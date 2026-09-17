from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import String, Text, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class SourceEnum(str, Enum):
    CALIL = "calil"
    VEGAS = "vegas"
    ZUK = "zuk"


class AuctionModel(Base):
    __tablename__ = "auctions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(128), index=True)  # ID no site de origem
    source: Mapped[str] = mapped_column(String(32), index=True)  # calil, vegas
    title: Mapped[str] = mapped_column(String(512))
    url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    lots: Mapped[list["LotModel"]] = relationship("LotModel", back_populates="auction", cascade="all, delete-orphan")


class LotModel(Base):
    __tablename__ = "lots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    auction_id: Mapped[int] = mapped_column(ForeignKey("auctions.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    minimum_bid: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    current_bid: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reference_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    raw_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON para dados extras
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    auction: Mapped["AuctionModel"] = relationship("AuctionModel", back_populates="lots")