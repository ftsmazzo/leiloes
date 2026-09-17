"""
Zuk (Portal Zuk / ex-Zukerman) — listagem pública de imóveis.
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

RE_ID = re.compile(r"/imovel/[^?]*/(\d+-\d+)")
RE_MONEY = re.compile(r"R\$\s*([\d.]+,\d{2})")


class ZukScraper(BaseScraper):
    source_name = "zuk"
    base_url = "https://www.portalzuk.com.br"

    async def scrape(self) -> list[ScrapedAuction]:
        by_id: dict[str, ScrapedLot] = {}
        paths = (
            "/leilao-de-imoveis/tl/todos-imoveis/leilao-judicial",
            "/leilao-de-imoveis",
        )
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=HEADERS) as client:
            await client.get(self.base_url)
            for path in paths:
                for page in range(1, 9):
                    url = f"{self.base_url}{path}"
                    if page > 1:
                        url = f"{url}?page={page}"
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
                external_id="zuk-abertos",
                source=self.source_name,
                title="Zuk — imóveis em leilão",
                url=f"{self.base_url}/leilao-de-imoveis",
                description=f"{len(lots)} lote(s) públicos",
                lots=lots,
            )
        ]


def lots_from_html(html: str, base_url: str) -> list[ScrapedLot]:
    soup = BeautifulSoup(html, "html.parser")
    lots: list[ScrapedLot] = []
    seen: set[str] = set()
    for card in soup.select(".card-property"):
        if card.select_one("span.card-property-encerrado"):
            continue
        lot = _card_to_lot(card, base_url)
        if not lot or lot.external_id in seen:
            continue
        seen.add(lot.external_id)
        lots.append(lot)
    return lots


def _card_to_lot(card: Tag, base_url: str) -> ScrapedLot | None:
    link = card.select_one("a[href*='/imovel/']")
    href = href_of(link)
    match = RE_ID.search(href)
    if not match:
        return None
    external_id = match.group(1)
    title_attr = ""
    if link and link.get("title"):
        title_attr = str(link.get("title"))
    tipo_el = card.select_one(".card-property-price-lote")
    tipo_label = text_of(tipo_el)
    addr = card.select_one(".card-property-address")
    addr_text = text_of(addr)
    title = (title_attr.split("|")[0].strip() or tipo_label or f"Lote {external_id}")[:512]
    city_link = addr.select_one("a") if addr else None
    cidade = text_of(city_link).split("/")[0].strip() if city_link else None
    if not cidade:
        cidade = cidade_from_text(addr_text, title)
    rua = ""
    if addr:
        spans = addr.select("span")
        if len(spans) >= 2:
            rua = text_of(spans[-1])
    current = None
    reference = None
    for li in card.select(".card-property-price"):
        raw = text_of(li.select_one(".card-property-price-value"))
        found = RE_MONEY.search(raw.replace("\xa0", " "))
        if not found:
            found = RE_MONEY.search(text_of(li))
        if not found:
            continue
        value = parse_br_currency(found.group(0))
        struck = li.select_one('[style*="line-through"]')
        if struck and reference is None:
            reference = value
        else:
            current = value
    if current is None:
        current = reference
    tipo = tipo_from_text(tipo_label, title)
    origem = origem_from_text(title_attr, tipo_label)
    foto = photo_bg(card.select_one("img[src]"))
    return ScrapedLot(
        external_id=external_id,
        title=title,
        description=addr_text[:2000] or None,
        category=tipo,
        minimum_bid=current,
        current_bid=current,
        reference_value=reference,
        url=abs_url(base_url, href),
        raw_data=extra_lot(
            title=title,
            cidade=cidade,
            endereco=rua or None,
            tipo=tipo,
            foto=foto,
            origem=origem,
        ),
    )
