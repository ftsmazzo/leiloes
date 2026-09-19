"""Campos comuns dos scrapers de listagem pública (sem GLiNER)."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from .extract import cidade_from_text, extra_json, parse_br_currency, tipo_from_text

__all__ = [
    "HEADERS",
    "cidade_from_text",
    "parse_br_currency",
    "parse_br_date",
    "tipo_from_text",
    "extra_json",
    "href_of",
    "abs_url",
    "photo_bg",
    "extra_lot",
    "text_of",
    "origem_from_text",
    "pracas_from_html",
    "pracas_from_tag",
    "merge_pracas",
]

RE_DATE = re.compile(r"(\d{2}/\d{2}/\d{4})\s*(?:às|as)?\s*(\d{2}:\d{2})?", re.I)
RE_PRACA_N = re.compile(r"(\d)\s*[ªa]\s*pra[cç]a", re.I)


def parse_br_date(s: Optional[str]) -> Optional[datetime]:
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


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _praca_n(blob: str) -> int | None:
    found = RE_PRACA_N.search(blob or "")
    return int(found.group(1)) if found else None


def _as_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and len(value) >= 16:
        try:
            return datetime.fromisoformat(value[:19])
        except ValueError:
            return None
    return None


def _praca_item(
    n: int,
    *,
    inicio: datetime | None = None,
    fim: datetime | None = None,
    valor: float | None = None,
    ativa: bool = False,
) -> dict[str, Any] | None:
    item: dict[str, Any] = {"n": n}
    if inicio:
        item["inicio"] = _iso(inicio)
    if fim:
        item["fim"] = _iso(fim)
    if valor and valor > 0:
        item["valor"] = valor
    if ativa:
        item["ativa"] = True
    if len(item) == 1:
        return None
    return item


def merge_pracas(old: Any, new: Any) -> list[dict[str, Any]]:
    """Junta listagem (início+fim) com a página do bem (só encerramento)."""
    by_n: dict[int, dict[str, Any]] = {}
    for bloco in (old, new):
        if not isinstance(bloco, list):
            continue
        for raw in bloco:
            if not isinstance(raw, dict) or not isinstance(raw.get("n"), int):
                continue
            cur = dict(by_n.get(raw["n"]) or {"n": raw["n"]})
            for key in ("inicio", "fim", "valor", "ativa"):
                val = raw.get(key)
                if val not in (None, "", False):
                    cur[key] = val
            by_n[raw["n"]] = cur
    return [by_n[n] for n in sorted(by_n)]


def _mark_ativa(pracas: list[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
    if any(p.get("ativa") for p in pracas):
        return pracas
    ref = now or datetime.now()
    ativa_n: int | None = None
    for p in pracas:
        start = _as_dt(p.get("inicio"))
        if start and start <= ref:
            ativa_n = p["n"]
    if ativa_n is None:
        return pracas
    for p in pracas:
        if p["n"] == ativa_n:
            p["ativa"] = True
        else:
            p.pop("ativa", None)
    return pracas


def pracas_from_tag(root: Tag, now: datetime | None = None) -> list[dict[str, Any]]:
    """1ª/2ª praça com data e valor, se o HTML público trouxer."""
    out: list[dict[str, Any]] = []
    for row in root.select(".card-date-row"):
        n = _praca_n(text_of(row.select_one(".card-instance-label")))
        dates = row.select(".card-instance-date li")
        if n is None or len(dates) < 2:
            continue
        item = _praca_item(
            n,
            inicio=parse_br_date(text_of(dates[0])),
            fim=parse_br_date(text_of(dates[1])) if len(dates) > 1 else None,
            valor=parse_br_currency(text_of(dates[2])) if len(dates) > 2 else None,
        )
        if item:
            out.append(item)
    if out:
        return _mark_ativa(sorted(out, key=lambda p: p["n"]), now)

    for block in root.select(".product-instance"):
        blob = text_of(block)
        n = _praca_n(blob)
        if n is None:
            continue
        classes = block.get("class") or []
        money_txt = ""
        for div in block.select("div"):
            txt = text_of(div)
            if "R$" in txt:
                money_txt = txt
                break
        item = _praca_item(
            n,
            fim=parse_br_date(text_of(block.select_one("strong")) or blob),
            valor=parse_br_currency(money_txt) if money_txt else None,
            ativa="active" in classes,
        )
        if item:
            out.append(item)
    if out:
        return _mark_ativa(sorted(out, key=lambda p: p["n"]), now)

    for inst in root.select(".instance"):
        blob = text_of(inst)
        n = _praca_n(blob)
        if n is None and inst.select_one(".card-first-instance-date"):
            n = 1
        if n is None:
            continue
        item = _praca_item(
            n,
            fim=parse_br_date(blob),
            valor=parse_br_currency(text_of(inst.select_one(".card-instance-value")) or blob),
        )
        if item:
            out.append(item)
    return _mark_ativa(sorted(out, key=lambda p: p["n"]), now)


def pracas_from_html(html: str, now: datetime | None = None) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html or "", "html.parser")
    return pracas_from_tag(soup, now=now)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0",
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

RE_BG = re.compile(r"url\((['\"]?)([^)'\"]+)\1\)", re.I)


def href_of(tag: Tag | None) -> str:
    if tag is None:
        return ""
    raw = tag.get("href")
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    return raw if isinstance(raw, str) else ""


def abs_url(base: str, href: str) -> str:
    if not href:
        return base
    if href.startswith("//"):
        return "https:" + href
    return urljoin(base, href.split("?")[0])


def photo_bg(tag: Tag | None) -> str | None:
    if tag is None:
        return None
    src = tag.get("src") or tag.get("data-bg") or tag.get("data-src")
    if isinstance(src, str) and src.startswith("http"):
        return src
    if isinstance(src, str) and src.startswith("//"):
        return "https:" + src
    style = tag.get("style")
    if isinstance(style, str):
        found = RE_BG.search(style)
        if found:
            url = found.group(2)
            if url.startswith("//"):
                url = "https:" + url
            if url.startswith("http"):
                return url
    return None


def extra_lot(
    *,
    title: str,
    cidade: str | None,
    endereco: str | None,
    tipo: str | None,
    foto: str | None,
    origem: str | None = None,
    pracas: list[dict[str, Any]] | None = None,
) -> str | None:
    extra: dict[str, Any] = {}
    if cidade:
        extra["cidade"] = cidade
    if tipo:
        extra["tipo"] = tipo
    if endereco:
        extra["endereco"] = endereco
    if foto:
        extra["foto"] = foto
    if origem:
        extra["origem"] = origem
    if pracas:
        extra["pracas"] = pracas
    return extra_json(extra)


def text_of(tag: Tag | None) -> str:
    return tag.get_text(" ", strip=True) if tag else ""


def origem_from_text(*parts: Any) -> str | None:
    blob = " ".join(str(p).lower() for p in parts if p)
    if "extra" in blob:
        return "extrajudicial"
    if "judicial" in blob:
        return "judicial"
    return None
