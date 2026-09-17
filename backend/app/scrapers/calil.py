"""
Calil via Superbid Exchange (loja 818).
Página pública. Sem login. Parser coberto por fixture — CI não bate no site.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

import httpx
from bs4 import BeautifulSoup

from .base import BaseScraper, ScrapedAuction, ScrapedLot

RE_LANCE_ATUAL = re.compile(r"Lance\s+atual:\s*R\$\s*([\d.,]+)", re.I)


def _as_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("name", "title", "description", "city"):
            inner = value.get(key)
            if isinstance(inner, str) and inner.strip():
                return inner.strip()
    return ""


def cidade_from_text(*parts: Any, allow_bare: bool = False) -> str | None:
    """Cidade/SP no título; nome nu só com allow_bare (city/cityName)."""
    for part in parts:
        text = _as_text(part)
        if not text:
            continue
        idx = re.search(r"/\s*SP\b", text, re.I)
        if idx:
            head = text[: idx.start()].strip()
            chunk = re.split(r"\s+[—–]\s+", head)[-1].strip()
            chunk = re.sub(r"^(?:.*\s)?(?:em|no|na)\s+", "", chunk, flags=re.I)
            chunk = re.sub(r"\s+", " ", chunk).strip(" -,")
            if 2 < len(chunk) <= 40:
                return chunk
            continue
        if allow_bare and "/" not in text and 2 < len(text) <= 40:
            return text
    return None


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


class CalilScraper(BaseScraper):
    source_name = "calil"
    base_url = "https://exchange.superbid.net"
    loja_url = "https://exchange.superbid.net/loja-oficial/calil-leiloes-818"

    async def scrape(self) -> list[ScrapedAuction]:
        all_lots: list[ScrapedLot] = []
        page = 1
        page_size = 30

        async with httpx.AsyncClient(
            timeout=25.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"},
        ) as client:
            while True:
                url = (
                    f"{self.loja_url}?filter=statusId:1;stores.id:818"
                    f"&searchType=opened&pageNumber={page}&pageSize={page_size}&orderBy=price:desc"
                )
                try:
                    r = await client.get(url)
                    r.raise_for_status()
                    html = r.text
                except Exception:
                    break

                lots = self.lots_from_html(html)
                if not lots:
                    break
                all_lots.extend(lots)
                if len(lots) < page_size:
                    break
                page += 1
                if page > 10:
                    break

        if not all_lots:
            return []
        return [
            ScrapedAuction(
                external_id="calil-superbid-818",
                source=self.source_name,
                title="Calil Leilões (Superbid Exchange)",
                url=self.loja_url,
                description=f"{len(all_lots)} ofertas abertas",
                starts_at=None,
                ends_at=None,
                lots=all_lots,
            )
        ]

    def lots_from_html(self, html: str) -> list[ScrapedLot]:
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
        offers = (
            page_props.get("initialOffers")
            or page_props.get("offers")
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
            for k in ("offers", "items", "data", "initialOffers", "searchResult"):
                found = self._find_offers_in_json(obj.get(k) or [], depth + 1)
                if found:
                    return found
        return []

    def _offer_item_to_lot(self, item: dict[str, Any]) -> Optional[ScrapedLot]:
        offer_id = str(item.get("id") or item.get("offerId") or item.get("productId") or "")
        title = _as_text(item.get("title") or item.get("name") or item.get("description"))[:512]
        if not title and not offer_id:
            return None
        friendly_url = _as_text(item.get("friendlyUrl") or item.get("slug"))
        url = f"{self.base_url}/oferta/{friendly_url}" if friendly_url else None
        price = _price_from_item(item)
        evaluation = item.get("evaluationValue") or item.get("referenceValue")
        if isinstance(evaluation, str):
            evaluation = parse_br_currency(evaluation)
        category = item.get("category")
        sub = item.get("subCategory")
        if not isinstance(category, str) and isinstance(sub, dict):
            category = sub.get("description")
        if not isinstance(category, str):
            category = None
        cidade = cidade_from_text(title, item.get("description"))
        if not cidade:
            cidade = cidade_from_text(item.get("city"), item.get("cityName"), allow_bare=True)
        extra = {"cidade": cidade} if cidade else {}
        desc = _as_text(item.get("description")) or None
        return ScrapedLot(
            external_id=offer_id or (friendly_url.split("-")[-1] if friendly_url else "unknown"),
            title=title or f"Oferta {offer_id}",
            description=desc,
            category=category,
            minimum_bid=price,
            current_bid=price,
            reference_value=float(evaluation) if isinstance(evaluation, (int, float)) else None,
            url=url,
            raw_data=json.dumps(extra, ensure_ascii=False) if extra else None,
        )

    def _parse_oferta_links(self, html: str) -> list[ScrapedLot]:
        soup = BeautifulSoup(html, "html.parser")
        seen: set[str] = set()
        lots: list[ScrapedLot] = []
        for a in soup.select('a[href*="/oferta/"]'):
            href = a.get("href") or ""
            if "exchange.superbid" in href or href.startswith("/oferta/"):
                full_url = href if href.startswith("http") else f"{self.base_url}{href}"
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
            extra = {"cidade": cidade} if cidade else {}
            lots.append(
                ScrapedLot(
                    external_id=external_id[:128],
                    title=title,
                    description=None,
                    category=None,
                    minimum_bid=current_bid,
                    current_bid=current_bid,
                    reference_value=None,
                    url=full_url,
                    raw_data=json.dumps(extra, ensure_ascii=False) if extra else None,
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
    formatted = item.get("formattedPrice")
    if isinstance(formatted, str):
        return parse_br_currency(formatted)
    return None
