"""Campos comuns dos scrapers de listagem pública (sem GLiNER)."""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin

from bs4 import Tag

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0",
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

RE_BG = re.compile(r"url\((['\"]?)([^)'\"]+)\1\)", re.I)

TIPO_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("veiculo", re.compile(r"\bve[ií]culo|\bmoto(?:cicleta)?\b|\bcarro\b", re.I)),
    ("apartamento", re.compile(r"\bapartament|\bapto\b", re.I)),
    ("casa", re.compile(r"\bcasa\b|\bsobrado\b|\bed[ií]cula\b", re.I)),
    ("terreno", re.compile(r"\bterreno\b|\b[aá]rea de terras\b|\bfazenda\b", re.I)),
    ("galpao", re.compile(r"\bgalp[aã]o\b", re.I)),
    ("chacara", re.compile(r"\bch[aá]cara\b", re.I)),
    ("imovel", re.compile(r"\bim[oó]ve", re.I)),
]


def parse_br_currency(s: str) -> float | None:
    if not s:
        return None
    cleaned = re.sub(r"[^\d,.-]", "", str(s))
    if not cleaned:
        return None
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def tipo_from_text(*parts: Any) -> str | None:
    blob = " ".join(str(p) for p in parts if p)
    if not blob:
        return None
    for name, pattern in TIPO_PATTERNS:
        if pattern.search(blob):
            return name
    return None


def cidade_from_text(*parts: Any) -> str | None:
    for part in parts:
        text = str(part).strip() if part else ""
        if not text:
            continue
        if "," in text:
            name = text.split(",")[0].strip()
            if 2 < len(name) <= 40:
                return name
        if "/" in text:
            name = text.split("/")[0].strip()
            if 2 < len(name) <= 40:
                return name
    return None


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


def extra_json(extra: dict[str, Any]) -> str | None:
    clean = {k: v for k, v in extra.items() if v not in (None, "", [], {})}
    if not clean:
        return None
    return json.dumps(clean, ensure_ascii=False)


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
