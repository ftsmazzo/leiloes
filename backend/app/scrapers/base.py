"""
Classe base para scrapers de leilões.
Cada site implementa um scraper e entra em registry.SOURCES.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ScrapedLot:
    external_id: str
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    minimum_bid: Optional[float] = None
    current_bid: Optional[float] = None
    reference_value: Optional[float] = None
    url: Optional[str] = None
    raw_data: Optional[str] = None


@dataclass
class ScrapedAuction:
    external_id: str
    source: str
    title: str
    url: Optional[str] = None
    description: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    lots: list[ScrapedLot] = field(default_factory=list)


class BaseScraper(ABC):
    source_name: str = ""

    @abstractmethod
    async def scrape(self) -> list[ScrapedAuction]:
        """Raspagem do site e retorno da lista de leilões normalizados."""
        pass
