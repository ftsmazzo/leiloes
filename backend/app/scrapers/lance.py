"""
Grupo Lance — listagem pública de imóveis judiciais.
Sem login. Parser coberto por fixture — CI não bate no site.
"""
from __future__ import annotations

import re
from datetime import datetime

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
    pracas_from_tag,
    text_of,
    tipo_from_text,
)

RE_ID = re.compile(r"-(\d{4,6})$")


def _active_praca_price(card: Tag, now: datetime | None = None) -> tuple[float | None, float | None]:
    """Lê as praças do card e devolve (preço da praça ativa agora, preço da 1ª).

    O Grupo Lance mostra o preço da 1ª praça em destaque (.card-price) mesmo
    quando o lote já está na 2ª/3ª praça com lance bem menor — sem isso o
    catálogo mostrava até 2x o valor que dá pra ofertar de verdade.
    """
    now = now or datetime.now()
    rows: list[tuple[datetime, float]] = []
    for p in pracas_from_tag(card, now=now):
        start = None
        if p.get("inicio"):
            try:
                start = datetime.fromisoformat(str(p["inicio"]))
            except ValueError:
                start = None
        valor = p.get("valor")
        if start is None or not isinstance(valor, (int, float)):
            continue
        rows.append((start, float(valor)))
    if not rows:
        return None, None
    rows.sort(key=lambda r: r[0])
    active = rows[0][1]
    for start, price in rows:
        if start <= now:
            active = price
    first = rows[0][1]
    avaliacao = first if len(rows) > 1 and first != active else None
    return active, avaliacao


class LanceScraper(BaseScraper):
    source_name = "lance"
    base_url = "https://www.grupolance.com.br"

    async def scrape(self) -> list[ScrapedAuction]:
        by_id: dict[str, ScrapedLot] = {}
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=HEADERS) as client:
            await client.get(self.base_url)
            for page in range(1, 9):
                url = f"{self.base_url}/imoveis"
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
                external_id="lance-abertos",
                source=self.source_name,
                title="Grupo Lance — imóveis judiciais",
                url=f"{self.base_url}/imoveis",
                description=f"{len(lots)} lote(s) públicos",
                lots=lots,
            )
        ]


def lots_from_html(html: str, base_url: str) -> list[ScrapedLot]:
    soup = BeautifulSoup(html, "html.parser")
    lots: list[ScrapedLot] = []
    seen: set[str] = set()
    for card in soup.select(".card-item"):
        if re.search(r"encerrado", text_of(card), re.I):
            continue
        lot = _card_to_lot(card, base_url)
        if not lot or lot.external_id in seen:
            continue
        seen.add(lot.external_id)
        lots.append(lot)
    return lots


def _card_to_lot(card: Tag, base_url: str) -> ScrapedLot | None:
    external_id = str(card.get("data-key") or "").strip()
    link = card.select_one("a.card-title[href], a.card-image[href]")
    href = href_of(link)
    if not external_id:
        found = RE_ID.search(href.rstrip("/").split("?")[0])
        if not found:
            return None
        external_id = found.group(1)
    title = text_of(card.select_one(".card-title")) or (link.get("title") if link else None) or f"Lote {external_id}"
    title = str(title)[:512]
    local = text_of(card.select_one(".card-locality"))
    cidade = cidade_from_text(local, title)
    price, avaliacao = _active_praca_price(card)
    if price is None:
        price = parse_br_currency(text_of(card.select_one(".card-price")))
    origem = origem_from_text(
        text_of(card.select_one('a[href*="judiciais"]')),
        href,
        text_of(card.select_one(".card-info")),
    )
    img = card.select_one("a.card-image")
    foto = photo_bg(img)
    tipo = tipo_from_text(title, href)
    return ScrapedLot(
        external_id=external_id,
        title=title,
        description=text_of(card)[:2000] or None,
        category=tipo,
        minimum_bid=price,
        current_bid=price,
        reference_value=avaliacao,
        url=abs_url(base_url, href) if href else f"{base_url}/imoveis",
        raw_data=extra_lot(
            title=title,
            cidade=cidade,
            endereco=None,
            tipo=tipo,
            foto=foto,
            origem=origem,
            pracas=pracas_from_tag(card) or None,
        ),
    )
