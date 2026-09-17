"""
Parser HTML do motor Soleon (Calil, Vegas e casas no mesmo layout).
Páginas públicas: /leiloes, /lotes/imovel, /leilao/{id}/lotes, /item/{id}/detalhes.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from .base import ScrapedLot
from .extract import cidade_from_text, extra_json, leilao_status, parse_br_currency, tipo_from_text

RE_ITEM = re.compile(r"/item/(\d+)/detalhes")
RE_LEILAO = re.compile(r"/leilao/(\d+)/lotes")
RE_LABEL = re.compile(
    r"(Cidade|Endere[cç]o|Matr[ií]cula|Comitente|Comarca)\s*:\s*(.+?)(?=\s*(?:Cidade|Endere[cç]o|Matr[ií]cula|Comitente|Comarca|Lance|Processo)\s*:|$)",
    re.I,
)
RE_LANCE = re.compile(r"Lance\s+Inicial[^R$]*R\$\s*([\d.,]+)", re.I)
RE_AVALIA = re.compile(
    r"avalia[cç][aã]o[^R$]{0,80}R\$\s*([\d.,]+)",
    re.I,
)
RE_BG_IMG = re.compile(r"background:\s*url\(['\"]?([^)'\"]+)", re.I)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0",
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9",
}


def _href(tag: Tag) -> str:
    raw = tag.get("href")
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    return raw if isinstance(raw, str) else ""


def _label_map(blob: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for match in RE_LABEL.finditer(blob):
        key = match.group(1).lower()
        val = re.sub(r"\s+", " ", match.group(2)).strip(" -,")
        if key.startswith("cidade"):
            out["cidade"] = val.split("/")[0].strip()
        elif key.startswith("endere"):
            out["endereco"] = val
        elif key.startswith("matr"):
            out["matricula"] = val
        elif key.startswith("comitente"):
            out["comitente"] = val
        elif key.startswith("comarca"):
            out["comarca"] = val
    return out


def _photo_from(tag: Tag) -> str | None:
    img = tag.select_one("img[src]")
    if img:
        src = img.get("src")
        if isinstance(src, str) and src.startswith("http") and "comitente" not in src:
            return src
    style = tag.get("style") if tag.has_attr("style") else None
    if not isinstance(style, str):
        styled = tag.select_one("[style*='background']")
        style = styled.get("style") if styled else None
    if isinstance(style, str):
        found = RE_BG_IMG.search(style)
        if found and found.group(1).startswith("http"):
            return found.group(1)
    return None


def _is_encerrado(text: str) -> bool:
    return leilao_status(text) == "encerrado"


def _lot_extra(
    *,
    title: str,
    blob: str,
    foto: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    labels = _label_map(blob)
    cidade = labels.get("cidade") or cidade_from_text(title, blob, labels.get("comarca"))
    tipo = tipo_from_text(title, blob, category)
    extra: dict[str, Any] = {}
    if cidade:
        extra["cidade"] = cidade
    if tipo:
        extra["tipo"] = tipo
    if labels.get("endereco"):
        extra["endereco"] = labels["endereco"]
    if labels.get("matricula"):
        extra["matricula"] = labels["matricula"]
    if foto:
        extra["foto"] = foto
    extra["status"] = leilao_status(title, blob)
    return extra


def lots_from_imovel_list(html: str, base_url: str) -> list[ScrapedLot]:
    """Cards da listagem /lotes/imovel (Calil) — já trazem cidade e endereço."""
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    lots: list[ScrapedLot] = []
    blocks = soup.select("div.lote") or soup.select(".card.shadow-sm")
    for block in blocks:
        text = block.get_text(" ", strip=True)
        if _is_encerrado(text) and "aberto para lances" not in text.lower():
            continue
        link = block.select_one('a[href*="/item/"]')
        if not link:
            continue
        href = _href(link)
        match = RE_ITEM.search(href)
        if not match:
            continue
        external_id = match.group(1)
        if external_id in seen:
            continue
        seen.add(external_id)
        h5 = block.select_one("h5")
        title = (h5.get_text(strip=True) if h5 else "") or f"Lote {external_id}"
        lance = None
        h4 = block.select_one("h4.mb-0")
        if h4 and "R$" in (h4.get_text() or ""):
            lance = parse_br_currency(h4.get_text())
        if lance is None:
            labeled = RE_LANCE.search(text)
            if labeled:
                lance = parse_br_currency(labeled.group(1))
        extra = _lot_extra(title=title, blob=text, foto=_photo_from(block))
        avalia = RE_AVALIA.search(text)
        reference = parse_br_currency(avalia.group(1)) if avalia else None
        lots.append(
            ScrapedLot(
                external_id=external_id,
                title=title[:512],
                description=text[:2000] if text else None,
                category=extra.get("tipo"),
                minimum_bid=lance,
                current_bid=lance,
                reference_value=reference,
                url=urljoin(base_url, href.split("?")[0]),
                raw_data=extra_json(extra),
            )
        )
    return lots


def lots_from_leiloes_cards(html: str, base_url: str) -> list[ScrapedLot]:
    """Cards .box-leilao que apontam para /item/{id} (Calil mistura lote e leilão)."""
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    lots: list[ScrapedLot] = []
    for card in soup.select(".card.box-leilao"):
        text = card.get_text(" ", strip=True)
        if _is_encerrado(text):
            continue
        if re.search(r"simula", text, re.I):
            continue
        link = card.select_one('a[href*="/item/"]')
        if not link:
            continue
        href = _href(link)
        match = RE_ITEM.search(href)
        if not match:
            continue
        external_id = match.group(1)
        if external_id in seen:
            continue
        seen.add(external_id)
        title_el = card.select_one("h6.card-title")
        title = (title_el.get_text(strip=True) if title_el else "") or f"Lote {external_id}"
        labeled = RE_LANCE.search(text)
        lance = parse_br_currency(labeled.group(1)) if labeled else None
        extra = _lot_extra(title=title, blob=text, foto=_photo_from(card))
        lots.append(
            ScrapedLot(
                external_id=external_id,
                title=title[:512],
                description=text[:2000],
                category=extra.get("tipo"),
                minimum_bid=lance,
                current_bid=lance,
                url=urljoin(base_url, href.split("?")[0]),
                raw_data=extra_json(extra),
            )
        )
    return lots


def lots_from_lotes_page(html: str, base_url: str) -> list[ScrapedLot]:
    """Página /leilao/{id}/lotes — agrupa âncoras do mesmo item."""
    soup = BeautifulSoup(html, "html.parser")
    groups: dict[str, list[Tag]] = {}
    order: list[str] = []
    for a in soup.select('a[href*="/item/"]'):
        href = _href(a)
        match = RE_ITEM.search(href)
        if not match:
            continue
        external_id = match.group(1)
        if external_id not in groups:
            groups[external_id] = []
            order.append(external_id)
        groups[external_id].append(a)
    result: list[ScrapedLot] = []
    for external_id in order:
        lot = _anchors_to_lot(external_id, groups[external_id], base_url)
        if lot:
            result.append(lot)
    return result


def _anchors_to_lot(external_id: str, anchors: list[Tag], base_url: str) -> Optional[ScrapedLot]:
    href = _href(anchors[0])
    full_url = urljoin(base_url, href.split("?")[0])
    title = ""
    lance = None
    texts: list[str] = []
    foto = None
    parent = anchors[0].find_parent("div", class_="lote") or anchors[0].find_parent("div", class_="card")
    blob_parent = parent.get_text(" ", strip=True) if parent else ""
    for a in anchors:
        texts.append(a.get_text(" ", strip=True))
        if not foto:
            foto = _photo_from(a)
        h5 = a.select_one("h5")
        if h5 and not title:
            candidate = h5.get_text(strip=True)
            if candidate and not re.match(r"Lance Inicial\b", candidate, re.I):
                title = candidate
        h4 = a.select_one("h4.mb-0")
        if h4 and lance is None and "R$" in (h4.get_text() or ""):
            lance = parse_br_currency(h4.get_text())
    blob = blob_parent or " ".join(filter(None, texts))
    if lance is None:
        labeled = RE_LANCE.search(blob)
        if labeled:
            lance = parse_br_currency(labeled.group(1))
    extra = _lot_extra(title=title, blob=blob, foto=foto)
    avalia = RE_AVALIA.search(blob)
    reference = parse_br_currency(avalia.group(1)) if avalia else None
    return ScrapedLot(
        external_id=external_id,
        title=(title or f"Lote {external_id}")[:512],
        description=blob[:2000] if blob else None,
        category=extra.get("tipo"),
        minimum_bid=lance,
        current_bid=lance,
        reference_value=reference,
        url=full_url,
        raw_data=extra_json(extra),
    )


def parse_item_detail(html: str, base_url: str, external_id: str) -> ScrapedLot:
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    og = soup.select_one('meta[property="og:title"]')
    if og and og.get("content"):
        title = str(og.get("content")).split(" - Lance")[0].strip()
    if not title:
        h = soup.select_one("h5")
        title = h.get_text(strip=True) if h else f"Lote {external_id}"
    blob = soup.get_text(" ", strip=True)
    extra = _lot_extra(title=title, blob=blob, foto=_photo_from(soup))
    labeled = RE_LANCE.search(blob)
    lance = parse_br_currency(labeled.group(1)) if labeled else None
    avalia = RE_AVALIA.search(blob)
    reference = parse_br_currency(avalia.group(1)) if avalia else None
    canonical = soup.select_one('link[rel="canonical"]')
    url = None
    if canonical and canonical.get("href"):
        url = str(canonical.get("href"))
    if not url:
        url = urljoin(base_url, f"/item/{external_id}/detalhes")
    return ScrapedLot(
        external_id=external_id,
        title=title[:512],
        description=blob[:2500],
        category=extra.get("tipo"),
        minimum_bid=lance,
        current_bid=lance,
        reference_value=reference,
        url=url,
        raw_data=extra_json(extra),
    )


def merge_lot(base: ScrapedLot, detail: ScrapedLot) -> ScrapedLot:
    extra = {}
    for raw in (base.raw_data, detail.raw_data):
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            extra.update({k: v for k, v in data.items() if v})
    return ScrapedLot(
        external_id=base.external_id,
        title=detail.title or base.title,
        description=detail.description or base.description,
        category=detail.category or base.category,
        minimum_bid=detail.minimum_bid if detail.minimum_bid is not None else base.minimum_bid,
        current_bid=detail.current_bid if detail.current_bid is not None else base.current_bid,
        reference_value=detail.reference_value if detail.reference_value is not None else base.reference_value,
        url=detail.url or base.url,
        raw_data=extra_json(extra),
    )


def needs_detail(lot: ScrapedLot) -> bool:
    extra = {}
    if lot.raw_data:
        try:
            parsed = json.loads(lot.raw_data)
            if isinstance(parsed, dict):
                extra = parsed
        except json.JSONDecodeError:
            extra = {}
    return not extra.get("cidade") or not extra.get("endereco")
