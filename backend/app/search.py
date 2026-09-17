"""
Filtro de lotes já persistidos (cidade, tipo, teto, texto).
Casa com o que o scraper gravou em raw_data/título/categoria/lance.
"""
from __future__ import annotations

import json
import unicodedata
from typing import Any

from app.scrapers.extract import IMOVEIS, format_card, tipo_from_text


TIPO_ALIASES: dict[str, set[str]] = {
    "imovel": IMOVEIS,
    "casa": {"casa"},
    "apartamento": {"apartamento", "apto"},
    "terreno": {"terreno"},
    "galpao": {"galpao", "galpão"},
    "chacara": {"chacara", "chácara"},
    "sala": {"sala"},
    "veiculo": {"veiculo", "veículo"},
}


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


def raw_dict(lot: Any) -> dict[str, Any]:
    raw = getattr(lot, "raw_data", None)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def cidade_of(lot: Any) -> str | None:
    cidade = raw_dict(lot).get("cidade")
    if isinstance(cidade, str) and cidade.strip():
        return cidade.strip()
    return None


def endereco_of(lot: Any) -> str | None:
    endereco = raw_dict(lot).get("endereco")
    if isinstance(endereco, str) and endereco.strip():
        return endereco.strip()
    return None


def tipo_of(lot: Any) -> str | None:
    tipo = raw_dict(lot).get("tipo")
    if isinstance(tipo, str) and tipo.strip():
        return tipo.strip()
    return tipo_from_text(getattr(lot, "title", None), getattr(lot, "category", None))


def card_fields(lot: Any) -> dict[str, Any]:
    return format_card(
        getattr(lot, "title", None) or "",
        getattr(lot, "description", None),
        raw_dict(lot),
    )


def foto_of(lot: Any) -> str | None:
    foto = raw_dict(lot).get("foto")
    if not isinstance(foto, str) or not foto.startswith("http"):
        return None
    if "facebook.com/tr" in foto or "ev=PageView" in foto:
        return None
    return foto


def lot_matches(
    lot: Any,
    *,
    cidade: str | None = None,
    tipo: str | None = None,
    teto: float | None = None,
    q: str | None = None,
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
        stored = card_fields(lot).get("tipo")
        wanted = normalize_txt(tipo)
        aliases = TIPO_ALIASES.get(wanted, {wanted})
        if not stored:
            return False
        if normalize_txt(str(stored)) not in aliases and not any(
            _token_in(str(stored), alias) for alias in aliases
        ):
            return False
    if teto is not None:
        bid = getattr(lot, "current_bid", None)
        if bid is None:
            bid = getattr(lot, "minimum_bid", None)
        if bid is None or bid > teto:
            return False
    if q and q.strip():
        card = card_fields(lot)
        blob = " ".join(
            part
            for part in (
                card.get("headline"),
                card.get("endereco"),
                card.get("bairro"),
                card.get("matricula"),
                card.get("cidade"),
                card.get("tipo"),
                card.get("area"),
                getattr(lot, "title", None),
            )
            if isinstance(part, str) and part
        )
        if not _token_in(blob, q) and normalize_txt(q) not in normalize_txt(blob):
            return False
    return True


def filter_lots(
    lots: list[Any],
    *,
    cidade: str | None = None,
    tipo: str | None = None,
    teto: float | None = None,
    q: str | None = None,
) -> list[Any]:
    return [lot for lot in lots if lot_matches(lot, cidade=cidade, tipo=tipo, teto=teto, q=q)]
