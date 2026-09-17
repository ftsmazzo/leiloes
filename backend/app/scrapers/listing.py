"""Campos comuns dos scrapers de listagem pública (sem GLiNER)."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urljoin

from bs4 import Tag

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
]

RE_DATE = re.compile(r"(\d{2}/\d{2}/\d{4})\s*(?:às|as)?\s*(\d{2}:\d{2})?", re.I)


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
