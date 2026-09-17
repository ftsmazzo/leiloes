"""
Calil Leilões — site próprio (Soleon), não Superbid Exchange.
A loja Superbid 818 está sem ofertas abertas; o catálogo vivo é calilleiloes.com.br.
Parser coberto por fixture — CI não bate no site.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

import httpx
from bs4 import BeautifulSoup

from .base import BaseScraper, ScrapedAuction, ScrapedLot
from .extract import cidade_from_text, extra_json, parse_br_currency, tipo_from_text
from .soleon import HEADERS, lots_from_imovel_list, lots_from_leiloes_cards

RE_LANCE_ATUAL = re.compile(r"Lance\s+atual:\s*R\$\s*([\d.,]+)", re.I)

# reexport para testes e present.py
__all__ = ["CalilScraper", "cidade_from_text"]


class CalilScraper(BaseScraper):
    source_name = "calil"
    base_url = "https://www.calilleiloes.com.br"

    async def scrape(self) -> list[ScrapedAuction]:
        by_id: dict[str, ScrapedLot] = {}
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=HEADERS) as client:
            await client.get(self.base_url)
            page = 1
            while page <= 12:
                url = f"{self.base_url}/lotes/imovel?tipo=imovel&page={page}"
                try:
                    r = await client.get(url)
                    r.raise_for_status()
                except Exception:
                    break
                found = lots_from_imovel_list(r.text, self.base_url)
                new = 0
                for lot in found:
                    if lot.external_id not in by_id:
                        by_id[lot.external_id] = lot
                        new += 1
                if not found or new == 0:
                    break
                page += 1
            try:
                listing = await client.get(f"{self.base_url}/leiloes")
                listing.raise_for_status()
                for lot in lots_from_leiloes_cards(listing.text, self.base_url):
                    if lot.external_id not in by_id:
                        by_id[lot.external_id] = lot
            except Exception:
                pass

        lots = list(by_id.values())
        if not lots:
            return []
        return [
            ScrapedAuction(
                external_id="calil-abertos",
                source=self.source_name,
                title="Calil Leilões — lotes em andamento",
                url=f"{self.base_url}/lotes/imovel",
                description=f"{len(lots)} lote(s) públicos",
                lots=lots,
            )
        ]

    def lots_from_html(self, html: str) -> list[ScrapedLot]:
        lots = lots_from_imovel_list(html, self.base_url)
        if not lots:
            lots = lots_from_leiloes_cards(html, self.base_url)
        if not lots:
            lots = self._parse_next_data(html)
        if not lots:
            lots = self._parse_oferta_links(html)
        return lots

    def _parse_next_data(self, html: str) -> list[ScrapedLot]:
        soup = BeautifulSoup(html, "html.parser")
        tag = soup.find("script", id="__NEXT_DATA__")
        raw = tag.string if tag else None
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, dict):
            return []
        props = data.get("props")
        page_props = props.get("pageProps") if isinstance(props, dict) else None
        if not isinstance(page_props, dict):
            page_props = {}
        data_block = page_props.get("data") if isinstance(page_props.get("data"), dict) else {}
        search = page_props.get("searchResult") if isinstance(page_props.get("searchResult"), dict) else {}
        offers_list = page_props.get("offersList") if isinstance(page_props.get("offersList"), dict) else {}
        offers = (
            page_props.get("initialOffers")
            or page_props.get("offers")
            or offers_list.get("offers")
            or data_block.get("offers")
            or search.get("offers")
            or []
        )
        if isinstance(offers, dict):
            offers = offers.get("items") or offers.get("data") or []
        if not isinstance(offers, list) or not offers:
            offers = self._find_offers_in_json(page_props)
        if not isinstance(offers, list):
            return []
        lots: list[ScrapedLot] = []
        for item in offers:
            if not isinstance(item, dict):
                continue
            try:
                lot = self._offer_item_to_lot(item)
            except Exception:
                continue
            if lot:
                lots.append(lot)
        return lots

    def _find_offers_in_json(self, obj: Any, depth: int = 0) -> list:
        if depth > 5:
            return []
        if isinstance(obj, list):
            if obj and isinstance(obj[0], dict):
                first = obj[0]
                if any(first.get(k) for k in ("id", "offerId", "productId")):
                    return obj
            for x in obj:
                found = self._find_offers_in_json(x, depth + 1)
                if found:
                    return found
        if isinstance(obj, dict):
            for k in ("offers", "items", "data", "initialOffers", "searchResult", "offersList"):
                found = self._find_offers_in_json(obj.get(k) or [], depth + 1)
                if found:
                    return found
        return []

    def _offer_item_to_lot(self, item: dict[str, Any]) -> Optional[ScrapedLot]:
        offer_id = str(item.get("id") or item.get("offerId") or item.get("productId") or "")
        title = (item.get("title") or item.get("name") or item.get("description") or "")
        if isinstance(title, dict):
            title = title.get("name") or ""
        title = str(title).strip()[:512]
        if not title and not offer_id:
            return None
        product = item.get("product") if isinstance(item.get("product"), dict) else {}
        loc = product.get("location") if isinstance(product.get("location"), dict) else {}
        city_raw = loc.get("city") if isinstance(loc, dict) else None
        cidade = cidade_from_text(title, item.get("description"), city_raw, allow_bare=False)
        if not cidade:
            cidade = cidade_from_text(item.get("city"), item.get("cityName"), city_raw, allow_bare=True)
        sub = product.get("subCategory") if isinstance(product.get("subCategory"), dict) else item.get("subCategory")
        category = item.get("category") if isinstance(item.get("category"), str) else None
        if not category and isinstance(sub, dict):
            category = sub.get("description")
        if not category:
            ptype = product.get("productType") if isinstance(product.get("productType"), dict) else None
            if isinstance(ptype, dict):
                category = ptype.get("description")
        tipo = tipo_from_text(title, category)
        extra = extra_json({"cidade": cidade, "tipo": tipo})
        desc = None
        if isinstance(item.get("description"), str):
            desc = item.get("description")
        elif isinstance(product.get("shortDesc"), str):
            desc = product.get("shortDesc")
        url = None
        friendly_url = item.get("friendlyUrl") or item.get("slug")
        if isinstance(friendly_url, str) and friendly_url.strip():
            url = f"https://exchange.superbid.net/oferta/{friendly_url.strip()}"
        elif offer_id:
            url = f"{self.base_url}/item/{offer_id}/detalhes"
        price = _price_from_item(item)
        evaluation = item.get("evaluationValue") or item.get("referenceValue")
        if isinstance(evaluation, str):
            evaluation = parse_br_currency(evaluation)
        detail = item.get("offerDetail") if isinstance(item.get("offerDetail"), dict) else {}
        if price is None:
            price = detail.get("currentMinBid") or detail.get("initialBidValue")
            if isinstance(price, (int, float)):
                price = float(price)
        return ScrapedLot(
            external_id=offer_id or "unknown",
            title=title or f"Oferta {offer_id}",
            description=desc,
            category=category if isinstance(category, str) else tipo,
            minimum_bid=float(price) if isinstance(price, (int, float)) else None,
            current_bid=float(price) if isinstance(price, (int, float)) else None,
            reference_value=float(evaluation) if isinstance(evaluation, (int, float)) else None,
            url=url,
            raw_data=extra,
        )

    def _parse_oferta_links(self, html: str) -> list[ScrapedLot]:
        soup = BeautifulSoup(html, "html.parser")
        seen: set[str] = set()
        lots: list[ScrapedLot] = []
        for a in soup.select('a[href*="/oferta/"]'):
            href = a.get("href") or ""
            if not isinstance(href, str):
                continue
            if "exchange.superbid" in href or href.startswith("/oferta/"):
                full_url = href if href.startswith("http") else f"https://exchange.superbid.net{href}"
            else:
                continue
            slug_id = href.strip("/").split("/")[-1]
            external_id = (slug_id.split("-")[-1] if "-" in slug_id else slug_id)[:128]
            if external_id in seen:
                continue
            seen.add(external_id)
            text = a.get_text(separator=" ", strip=True)
            title = (a.get("aria-label") or text or f"Oferta {external_id}")[:512]
            if len(title) > 200:
                title = title[:197] + "..."
            lance_match = RE_LANCE_ATUAL.search(text)
            current_bid = parse_br_currency(lance_match.group(1)) if lance_match else None
            cidade = cidade_from_text(title, text)
            extra = extra_json({"cidade": cidade, "tipo": tipo_from_text(title)})
            lots.append(
                ScrapedLot(
                    external_id=external_id[:128],
                    title=title,
                    url=full_url,
                    minimum_bid=current_bid,
                    current_bid=current_bid,
                    raw_data=extra,
                )
            )
        return lots


def _price_from_item(item: dict[str, Any]) -> Optional[float]:
    for key in ("currentPrice", "price", "minimumBid", "lanceAtual", "currentBid"):
        val = item.get(key)
        if val is None:
            continue
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            return parse_br_currency(val)
        if isinstance(val, dict):
            inner = val.get("value") or val.get("amount")
            if isinstance(inner, (int, float)):
                return float(inner)
    formatted = item.get("formattedPrice") or item.get("priceFormatted")
    if isinstance(formatted, str):
        return parse_br_currency(formatted)
    return None
