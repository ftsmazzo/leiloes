"""
Vegas Leilões — páginas públicas Soleon.
Listagem /leiloes. Lotes em /leilao/{id}/lotes. Detalhe /item/{id}/detalhes se faltar cidade/endereço.
Sem login. Parser coberto por fixture — CI não bate no site.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from .base import BaseScraper, ScrapedAuction, ScrapedLot
from .extract import parse_br_currency
from .soleon import (
    HEADERS,
    RE_LEILAO,
    _href,
    lots_from_lotes_page,
    merge_lot,
    needs_detail,
    parse_item_detail,
)

RE_DATE = re.compile(r"(\d{2}/\d{2}/\d{4})\s*(?:às|as)?\s*(\d{2}:\d{2})?", re.I)


def parse_vegas_date(s: str) -> Optional[datetime]:
    if not s:
        return None
    m = RE_DATE.search(s)
    if not m:
        return None
    try:
        day, month, year = m.group(1).split("/")
        hour, minute = (m.group(2) or "00:00").split(":")
        return datetime(int(year), int(month), int(day), int(hour), int(minute))
    except (ValueError, IndexError):
        return None


def cidade_from_vegas(*parts: str | None) -> str | None:
    from .extract import cidade_from_text

    return cidade_from_text(*parts)


class VegasScraper(BaseScraper):
    source_name = "vegas"
    base_url = "https://www.vegasleiloes.com.br"

    async def scrape(self) -> list[ScrapedAuction]:
        auctions: list[ScrapedAuction] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=HEADERS) as client:
            await client.get(self.base_url)
            r = await client.get(f"{self.base_url}/leiloes")
            r.raise_for_status()
            for auction in self.auctions_from_html(r.text):
                if auction.external_id in seen_ids:
                    continue
                seen_ids.add(auction.external_id)
                auctions.append(auction)

            detail_left = 25
            for auction in auctions:
                if not auction.external_id.isdigit():
                    continue
                lotes_url = f"{self.base_url}/leilao/{auction.external_id}/lotes"
                try:
                    r = await client.get(lotes_url)
                    r.raise_for_status()
                    auction.lots = lots_from_lotes_page(r.text, self.base_url)
                except Exception as exc:
                    print(f"Vegas lotes {auction.external_id}: {exc}")
                    auction.lots = []
                if detail_left <= 0:
                    continue
                missing = [lot for lot in auction.lots if needs_detail(lot)]
                for lot in missing:
                    if detail_left <= 0:
                        break
                    try:
                        det = await client.get(f"{self.base_url}/item/{lot.external_id}/detalhes")
                        det.raise_for_status()
                        parsed = parse_item_detail(det.text, self.base_url, lot.external_id)
                        filled = merge_lot(lot, parsed)
                        idx = auction.lots.index(lot)
                        auction.lots[idx] = filled
                        detail_left -= 1
                    except Exception as exc:
                        print(f"Vegas detalhe {lot.external_id}: {exc}")

        return auctions

    def auctions_from_html(self, html: str) -> list[ScrapedAuction]:
        soup = BeautifulSoup(html, "html.parser")
        result: list[ScrapedAuction] = []
        for card in soup.select(".card.box-leilao"):
            auction = self._card_to_auction(card)
            if auction:
                result.append(auction)
        return result

    def lots_from_html(self, html: str) -> list[ScrapedLot]:
        return lots_from_lotes_page(html, self.base_url)

    def _card_to_auction(self, card: Tag) -> Optional[ScrapedAuction]:
        label = card.select_one(".label_leilao")
        label_text = label.get_text(strip=True) if label else ""
        if re.search(r"encerrado", label_text, re.I):
            return None
        link = card.select_one('a[href*="/leilao/"]')
        if not link:
            return None
        href = _href(link)
        full_url = urljoin(self.base_url, href)
        m = RE_LEILAO.search(full_url)
        if not m:
            return None
        title_el = card.select_one("h6.card-title")
        title = (title_el.get_text(strip=True) if title_el else "") or "Leilão Vegas"
        if re.search(r"simula", title, re.I):
            return None
        parts = [p.get_text(" ", strip=True) for p in card.select("p.mb-0")]
        parts += [d.get_text(" ", strip=True) for d in card.select(".card-text.mb-auto div")]
        description = " | ".join(filter(None, parts)) or None
        starts_at = None
        for text in parts:
            if re.search(r"leil[aã]o", text, re.I):
                starts_at = parse_vegas_date(text)
                if starts_at:
                    break
        return ScrapedAuction(
            external_id=m.group(1),
            source=self.source_name,
            title=title[:512],
            url=full_url,
            description=description[:1024] if description else None,
            starts_at=starts_at,
            ends_at=None,
            lots=[],
        )
