"""
Vegas Leilões — páginas públicas.
Listagem /leiloes (em andamento). Lotes em /leilao/{id}/lotes.
Sem login. Parser coberto por fixture — CI não bate no site.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from .base import BaseScraper, ScrapedAuction, ScrapedLot

RE_CIDADE_LABEL = re.compile(r"Cidade:\s*([^\n<]+)", re.I)
RE_ITEM = re.compile(r"/item/(\d+)/detalhes")
RE_LEILAO = re.compile(r"/leilao/(\d+)/lotes")
RE_DATE = re.compile(r"(\d{2}/\d{2}/\d{4})\s*(?:às|as)?\s*(\d{2}:\d{2})?", re.I)
RE_LANCE_LABEL = re.compile(r"Lance Inicial[^R$]*R\$\s*([\d.,]+)", re.I)


def _href(tag: Tag) -> str:
    raw = tag.get("href")
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    return raw if isinstance(raw, str) else ""


def parse_br_currency(s: str) -> Optional[float]:
    if not s:
        return None
    s = re.sub(r"[^\d,.-]", "", str(s))
    if not s:
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


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
    blob = " ".join(p for p in parts if p)
    labeled = RE_CIDADE_LABEL.search(blob)
    if labeled:
        name = re.sub(r"\s+", " ", labeled.group(1)).split("/")[0].strip(" -,")
        return name or None
    idx = re.search(r"/\s*SP\b", blob, re.I)
    if not idx:
        return None
    head = blob[: idx.start()].strip()
    chunk = re.split(r"\s+[—–]\s+", head)[-1].strip()
    chunk = re.sub(r"^(?:.*\s)?(?:em|no|na)\s+", "", chunk, flags=re.I)
    chunk = re.sub(r"\s+", " ", chunk).strip(" -,")
    if 2 < len(chunk) <= 40:
        return chunk
    return None


class VegasScraper(BaseScraper):
    source_name = "vegas"
    base_url = "https://www.vegasleiloes.com.br"

    async def scrape(self) -> list[ScrapedAuction]:
        auctions: list[ScrapedAuction] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"},
        ) as client:
            r = await client.get(f"{self.base_url}/leiloes")
            r.raise_for_status()
            for auction in self.auctions_from_html(r.text):
                if auction.external_id in seen_ids:
                    continue
                seen_ids.add(auction.external_id)
                auctions.append(auction)

            for auction in auctions:
                if not auction.external_id.isdigit():
                    continue
                lotes_url = f"{self.base_url}/leilao/{auction.external_id}/lotes"
                try:
                    r = await client.get(lotes_url)
                    r.raise_for_status()
                    auction.lots = self.lots_from_html(r.text)
                except Exception as exc:
                    print(f"Vegas lotes {auction.external_id}: {exc}")
                    auction.lots = []

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
        soup = BeautifulSoup(html, "html.parser")
        groups: dict[str, list[Tag]] = {}
        order: list[str] = []
        for a in soup.select('a[href*="/item/"]'):
            href = _href(a)
            m = RE_ITEM.search(href)
            if not m:
                continue
            external_id = m.group(1)
            if external_id not in groups:
                groups[external_id] = []
                order.append(external_id)
            groups[external_id].append(a)
        result: list[ScrapedLot] = []
        for external_id in order:
            lot = self._anchors_to_lot(external_id, groups[external_id])
            if lot:
                result.append(lot)
        return result

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

    def _anchors_to_lot(self, external_id: str, anchors: list[Tag]) -> Optional[ScrapedLot]:
        href = _href(anchors[0])
        full_url = urljoin(self.base_url, href.split("?")[0])
        title = ""
        lance = None
        texts: list[str] = []
        for a in anchors:
            texts.append(a.get_text(" ", strip=True))
            h5 = a.select_one("h5")
            if h5 and not title:
                candidate = h5.get_text(strip=True)
                if candidate and not re.match(r"Lance Inicial\b", candidate, re.I):
                    title = candidate
            h4 = a.select_one("h4.mb-0")
            if h4 and lance is None and "R$" in (h4.get_text() or ""):
                lance = parse_br_currency(h4.get_text())
        blob = " ".join(filter(None, texts))
        if lance is None:
            labeled = RE_LANCE_LABEL.search(blob)
            if labeled:
                lance = parse_br_currency(labeled.group(1))
        cidade = cidade_from_vegas(blob, title)
        extra = {"cidade": cidade} if cidade else {}
        return ScrapedLot(
            external_id=external_id,
            title=(title or f"Lote {external_id}")[:512],
            description=blob[:2000] if blob else None,
            category=None,
            minimum_bid=lance,
            current_bid=lance,
            reference_value=None,
            url=full_url,
            raw_data=json.dumps(extra, ensure_ascii=False) if extra else None,
        )
