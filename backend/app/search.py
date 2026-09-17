"""
Filtro de lotes já persistidos (cidade, tipo, teto).
Casa com o que o scraper gravou em raw_data/título/categoria/lance.
"""
from __future__ import annotations

import json
import unicodedata
from typing import Any


def normalize_txt(value: str) -> str:
    nfd = unicodedata.normalize("NFD", value)
    stripped = "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")
    for sep in ("/", "|", "—", "–", "-", ",", ";"):
        stripped = stripped.replace(sep, " ")
    return " ".join(stripped.lower().split())


def _token_in(haystack: str, query: str) -> bool:
    h = normalize_txt(haystack)
    q = normalize_txt(query)
    if not q:
        return True
    if h == q:
        return True
    padded = f" {h} "
    return f" {q} " in padded or h.startswith(q + " ") or h.endswith(" " + q)


def cidade_of(lot: Any) -> str | None:
    raw = getattr(lot, "raw_data", None)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    cidade = data.get("cidade")
    if isinstance(cidade, str) and cidade.strip():
        return cidade.strip()
    return None


def lot_matches(
    lot: Any,
    *,
    cidade: str | None = None,
    tipo: str | None = None,
    teto: float | None = None,
) -> bool:
    if cidade and cidade.strip():
        stored = cidade_of(lot)
        if stored:
            if not _token_in(stored, cidade):
                return False
        else:
            title = getattr(lot, "title", None) or ""
            if not _token_in(title, cidade):
                return False
    if tipo and tipo.strip():
        blob = " ".join(
            part for part in (getattr(lot, "category", None), getattr(lot, "title", None)) if part
        )
        if not _token_in(blob, tipo):
            return False
    if teto is not None:
        bid = getattr(lot, "current_bid", None)
        if bid is None:
            bid = getattr(lot, "minimum_bid", None)
        if bid is None or bid > teto:
            return False
    return True


def filter_lots(
    lots: list[Any],
    *,
    cidade: str | None = None,
    tipo: str | None = None,
    teto: float | None = None,
) -> list[Any]:
    return [lot for lot in lots if lot_matches(lot, cidade=cidade, tipo=tipo, teto=teto)]
