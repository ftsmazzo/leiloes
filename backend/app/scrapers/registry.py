"""Registro de fontes. Nova fonte: classe BaseScraper + uma linha em SOURCES (Issue #16)."""

from app.scrapers.base import BaseScraper
from app.scrapers.calil import CalilScraper
from app.scrapers.vegas import VegasScraper
from app.scrapers.zuk import ZukScraper

SOURCES: list[type[BaseScraper]] = [
    CalilScraper,
    VegasScraper,
    ZukScraper,
]


def all_scrapers() -> list[BaseScraper]:
    return [cls() for cls in SOURCES]


def source_names() -> list[str]:
    return [cls.source_name for cls in SOURCES]
