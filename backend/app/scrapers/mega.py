"""
Mega Leilões — listagem pública de imóveis.
Sem login. Parser coberto por fixture — CI não bate no site.
"""
from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup, Tag

from .base import BaseScraper, ScrapedAuction, ScrapedLot
from .listing import (
    HEADERS,
    abs_url,
    cidade_from_text,
    extra_lot,
    href_of,
    origem_from_text,
    parse_br_currency,
    photo_bg,
    text_of,
    tipo_from_text,
)

RE_LOT_ID = re.compile(r"\b([XJ]\d{4,6})\b", re.I)
RE_HREF_ID = re.compile(r"-([xj]\d{4,6})(?:\?|$)", re.I)


class MegaScraper(BaseScraper):
    source_name = "mega"
    base_url = "https://www.megaleiloes.com.br"

    async def scrape(self) -> list[ScrapedAuction]:
        by_id: dict[str, ScrapedLot] = {}
        paths = ("/?imoveis=1", "/leiloes-judiciais")
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=HEADERS) as client:
            await client.get(self.base_url)
            for path in paths:
                for page in range(1, 9):
                    url = f"{self.base_url}{path}"
                    sep = "&" if "?" in path else "?"
                    if page > 1:
                        url = f"{url}{sep}pagina={page}"
                    try:
                        r = await client.get(url)
                        r.raise_for_status()
                    except Exception:
                        break
                    found = lots_from_html(r.text, self.base_url)
                    new = 0
                    for lot in found:
                        if lot.external_id not in by_id:
                            by_id[lot.external_id] = lot
                            new += 1
                    if not found or new == 0:
                        break
        lots = list(by_id.values())
        if not lots:
            return []
        return [
            ScrapedAuction(
                external_id="mega-abertos",
                source=self.source_name,
                title="Mega Leilões — imóveis",
                url=f"{self.base_url}/?imoveis=1",
                description=f"{len(lots)} lote(s) públicos",
                lots=lots,
            )
        ]


def lots_from_html(html: str, base_url: str) -> list[ScrapedLot]:
    soup = BeautifulSoup(html, "html.parser")
    lots: list[ScrapedLot] = []
    seen: set[str] = set()
    for card in soup.select(".card"):
        classes = card.get("class") or []
        if "card-auction" in classes:
            continue
        if "open" not in classes and re.search(r"encerrado", text_of(card), re.I):
            continue
        lot = _card_to_lot(card, base_url)
        if not lot or lot.external_id in seen:
            continue
        seen.add(lot.external_id)
        lots.append(lot)
    return lots


def _card_to_lot(card: Tag, base_url: str) -> ScrapedLot | None:
    number = text_of(card.select_one(".card-number"))
    match = RE_LOT_ID.search(number)
    link = card.select_one("a.card-title[href], a.card-image[href], a[href*='/imoveis/']")
    href = href_of(link)
    if not match:
        found = RE_HREF_ID.search(href)
        if not found:
            return None
        match = found
    external_id = match.group(1).upper()
    if re.search(r"/veiculos|/motos|/caminho", href, re.I):
        return None
    title = text_of(card.select_one(".card-title")) or f"Lote {external_id}"
    if tipo_from_text(title) == "veiculo":
        return None
    local = text_of(card.select_one(".card-locality"))
    cidade = cidade_from_text(local, title)
    price = parse_br_currency(text_of(card.select_one(".card-price")) or text_of(card.select_one(".card-instance-value")))
    origem_el = card.select_one(".card-instance-title a")
    origem = origem_from_text(text_of(origem_el), href)
    foto = photo_bg(card.select_one("a.card-image")) or photo_bg(card.select_one("img[src]"))
    tipo = tipo_from_text(title, href)
    return ScrapedLot(
        external_id=external_id,
        title=title[:512],
        description=text_of(card)[:2000] or None,
        category=tipo,
        minimum_bid=price,
        current_bid=price,
        url=abs_url(base_url, href) if href else f"{base_url}/{external_id}",
        raw_data=extra_lot(
            title=title,
            cidade=cidade,
            endereco=None,
            tipo=tipo,
            foto=foto,
            origem=origem,
        ),
    )
