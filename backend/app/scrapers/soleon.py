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
from .listing import merge_pracas, pracas_from_tag

RE_ITEM = re.compile(r"/item/(\d+)/detalhes")
RE_LEILAO = re.compile(r"/leilao/(\d+)/lotes")
_LABEL = (
    r"Cidade|Endere[cç]o|Matr[ií]cula|Comitente|Comarca|Processo|"
    r"[ÁA]rea(?:\s+(?:privativa|constru[ií]da|[úu]til|do\s+terreno|total))?|"
    r"Ocupa[cç][aã]o|D[eé]bitos?(?:\s+condominiais)?|IPTU|Condom[ií]nio|"
    r"Descri[cç][aã]o(?:\s+do\s+im[oó]vel)?|Tipo(?:\s+do\s+bem)?"
)
RE_LABEL = re.compile(
    rf"({_LABEL})\s*:\s*(.+?)(?=\s*(?:{_LABEL}|Lance)\s*:|$)",
    re.I,
)
RE_LABEL_TAG = re.compile(rf"^({_LABEL})\s*:?\s*$", re.I)
RE_MONEY_LABEL = re.compile(r"R\$\s*([\d.]+,\d{2})")
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


def _money_in(val: str) -> Optional[float]:
    found = RE_MONEY_LABEL.search(val or "")
    if found:
        return parse_br_currency(found.group(1))
    return parse_br_currency(val)


def _ocupacao_of(val: str) -> Optional[str]:
    clip = re.sub(r"\s+", " ", val or "").strip()[:80]
    low = clip.lower()
    if not clip:
        return None
    if re.search(r"caso|eventual|se houver|hip[oó]tese|se o im", low):
        return None
    if re.search(r"desocupad|im[oó]vel\s+vazi|n[aã]o\s+ocupad", low):
        return "desocupado"
    if re.search(r"\bocupad[oa]\b", low):
        return "ocupado"
    return None


def _put_label(out: dict[str, Any], key: str, val: str) -> None:
    if not val:
        return
    k = key.lower()
    if k.startswith("cidad"):
        name = val.split("/")[0].strip()
        if 2 < len(name) <= 40:
            out["cidade"] = name
    elif k.startswith("endere"):
        out["endereco"] = val[:120]
    elif k.startswith("matr"):
        out["matricula"] = val[:40]
    elif k.startswith("comitente"):
        out["comitente"] = val[:80]
    elif k.startswith("comarca"):
        out["comarca"] = val[:40]
    elif k.startswith("process"):
        from app.juridico import RE_CNJ, format_cnj

        found = RE_CNJ.search(val)
        if found:
            out["processo_cnj"] = format_cnj(found.group(1))
    elif k.startswith("área") or k.startswith("area"):
        out["area"] = val[:40]
    elif k.startswith("ocupa"):
        occ = _ocupacao_of(val)
        if occ:
            out["ocupacao"] = occ
    elif k.startswith("iptu"):
        money = _money_in(val)
        if money and money > 0:
            out.setdefault("dividas", {})["iptu"] = money
    elif "débito" in k or "debito" in k or k.startswith("condom"):
        money = _money_in(val)
        if money and money > 0:
            out.setdefault("dividas", {})["condominio"] = money
    elif k.startswith("descri"):
        out["descricao"] = val[:500]


def _label_map(blob: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for match in RE_LABEL.finditer(blob or ""):
        val = re.sub(r"\s+", " ", match.group(2)).strip(" -,")
        _put_label(out, match.group(1), val)
    return out


def _labels_from_soup(soup: BeautifulSoup) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for tag in soup.find_all(["b", "strong"]):
        name = re.sub(r"\s+", " ", tag.get_text(" ", strip=True)).strip()
        if not RE_LABEL_TAG.match(name.rstrip(":")) and not RE_LABEL_TAG.match(name):
            continue
        key = name.rstrip(":").strip()
        parts: list[str] = []
        nxt = tag.next_sibling
        while nxt is not None:
            nome = getattr(nxt, "name", None)
            if nome in ("b", "strong", "h5", "h6"):
                break
            if nome == "br":
                nxt = nxt.next_sibling
                continue
            if isinstance(nxt, str):
                text = nxt.strip()
            elif nome in ("p", "div"):
                break
            else:
                text = nxt.get_text(" ", strip=True) if hasattr(nxt, "get_text") else ""
            if text:
                parts.append(text)
            nxt = nxt.next_sibling
        val = re.sub(r"\s+", " ", " ".join(parts)).strip(" -,")
        _put_label(out, key, val)
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
    root: Tag | None = None,
) -> dict[str, Any]:
    labels = _label_map(blob)
    if root is not None:
        for key, val in _labels_from_soup(root).items():
            if key == "dividas" and isinstance(val, dict):
                merged = dict(labels.get("dividas") or {})
                merged.update(val)
                labels["dividas"] = merged
            elif val and not labels.get(key):
                labels[key] = val
    cidade = labels.get("cidade") or cidade_from_text(title, blob, labels.get("comarca"))
    tipo = tipo_from_text(title, blob, category)
    extra: dict[str, Any] = {}
    if cidade:
        extra["cidade"] = cidade
    if tipo:
        extra["tipo"] = tipo
    for key in ("endereco", "matricula", "comitente", "comarca", "processo_cnj", "area", "ocupacao", "descricao"):
        if labels.get(key):
            extra[key] = labels[key]
    if isinstance(labels.get("dividas"), dict) and labels["dividas"]:
        extra["dividas"] = labels["dividas"]
    if foto:
        extra["foto"] = foto
    extra["status"] = leilao_status(title, blob)
    pracas = pracas_from_tag(root) if root is not None else []
    if pracas:
        extra["pracas"] = pracas
    return extra


def fatos_from_html(html: str) -> dict[str, Any]:
    """Rótulos públicos da página do bem — sem baixar PDF."""
    if not html or not str(html).strip():
        return {}
    soup = BeautifulSoup(html, "html.parser")
    extra = _lot_extra(title="", blob=soup.get_text(" ", strip=True), root=soup)
    extra.pop("status", None)
    extra.pop("foto", None)
    extra.pop("tipo", None)
    extra.pop("pracas", None)
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
        extra = _lot_extra(title=title, blob=text, foto=_photo_from(block), root=block)
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
        extra = _lot_extra(title=title, blob=text, foto=_photo_from(card), root=card)
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
    extra = _lot_extra(title=title, blob=blob, foto=foto, root=parent)
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


DETAIL_CAP = 40


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
    extra = _lot_extra(title=title, blob=blob, foto=_photo_from(soup), root=soup)
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
    extra: dict[str, Any] = {}
    pracas: list = []
    for raw in (base.raw_data, detail.raw_data):
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            pracas = merge_pracas(pracas, data.get("pracas"))
            extra.update({k: v for k, v in data.items() if v and k != "pracas"})
    if pracas:
        extra["pracas"] = pracas
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


def _lot_extra_dict(lot: ScrapedLot) -> dict[str, Any]:
    if not lot.raw_data:
        return {}
    try:
        parsed = json.loads(lot.raw_data)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def needs_detail(lot: ScrapedLot) -> bool:
    """Abre /item quando faltam 1ª e 2ª praça, processo, cidade ou endereço."""
    extra = _lot_extra_dict(lot)
    pracas = extra.get("pracas") if isinstance(extra.get("pracas"), list) else []
    ns = {p.get("n") for p in pracas if isinstance(p, dict)}
    tem_pracas = 1 in ns and 2 in ns
    tem_processo = bool(extra.get("processo_cnj"))
    tem_endereco = bool(extra.get("cidade") and extra.get("endereco"))
    return not tem_pracas or not tem_processo or not tem_endereco


def fill_item_details(
    lots: list[ScrapedLot],
    *,
    base_url: str,
    fetch_html,
    cap: int = DETAIL_CAP,
) -> list[ScrapedLot]:
    """Completa cards rasos com a página pública do bem. Sem PDF."""
    left = cap
    out = list(lots)
    for i, lot in enumerate(out):
        if left <= 0:
            break
        if not needs_detail(lot):
            continue
        url = (lot.url or f"{base_url.rstrip('/')}/item/{lot.external_id}/detalhes").split("?")[0]
        try:
            html = fetch_html(url)
        except Exception as exc:
            print(f"detalhe {lot.external_id}: {exc}")
            continue
        out[i] = merge_lot(lot, parse_item_detail(html, base_url, lot.external_id))
        left -= 1
    return out


async def fill_item_details_async(
    lots: list[ScrapedLot],
    *,
    client,
    base_url: str,
    cap: int = DETAIL_CAP,
) -> tuple[list[ScrapedLot], int]:
    used = 0
    left = cap
    out = list(lots)
    for i, lot in enumerate(out):
        if left <= 0:
            break
        if not needs_detail(lot):
            continue
        url = (lot.url or f"{base_url.rstrip('/')}/item/{lot.external_id}/detalhes").split("?")[0]
        try:
            r = await client.get(url)
            r.raise_for_status()
            out[i] = merge_lot(lot, parse_item_detail(r.text, base_url, lot.external_id))
            left -= 1
            used += 1
        except Exception as exc:
            print(f"detalhe {lot.external_id}: {exc}")
    return out, used
