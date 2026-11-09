"""
Comparáveis de venda (Zap/VivaReal) via Apify — só na avaliação sob demanda.

FipeZap cobre 56 cidades e só apto. Interior e terreno/casa caem aqui.
Actor: gio21/vivareal-zap-scraper. Token em APIFY_TOKEN. Cache por
cidade+tipo no lote (não cobra de novo na reavaliação). Não roda no scrape.
"""
from __future__ import annotations

import os
import re
import statistics
from pathlib import Path
from typing import Any, Optional, Union

import httpx
from dotenv import dotenv_values

from app.datajud import tribunal_alias
from app.scrapers.market_price import _area_m2, _fold

_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"

ACTOR = "gio21~vivareal-zap-scraper"
APIFY_URL = f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items"
TIMEOUT = 90.0
MAX_ITEMS = 12
MIN_LISTINGS = 3

UF_TRIBUNAL = {
    "tjac": "ac",
    "tjal": "al",
    "tjap": "ap",
    "tjam": "am",
    "tjba": "ba",
    "tjce": "ce",
    "tjdft": "df",
    "tjes": "es",
    "tjgo": "go",
    "tjma": "ma",
    "tjmt": "mt",
    "tjms": "ms",
    "tjmg": "mg",
    "tjpa": "pa",
    "tjpb": "pb",
    "tjpr": "pr",
    "tjpe": "pe",
    "tjpi": "pi",
    "tjrj": "rj",
    "tjrn": "rn",
    "tjrs": "rs",
    "tjro": "ro",
    "tjrr": "rr",
    "tjsc": "sc",
    "tjse": "se",
    "tjsp": "sp",
    "tjto": "to",
}

# terreno_residencial: o actor devolve lista vazia até em São Paulo.
TIPO_PATH = {
    "apartamento": "apartamento_residencial",
    "casa": "casa_residencial",
}

RE_SLUG = re.compile(r"[^a-z0-9]+")


def _api_token() -> str:
    token = (os.getenv("APIFY_TOKEN") or os.getenv("APIFY_API_TOKEN") or "").strip()
    if token:
        return token
    vals = dotenv_values(_ENV_FILE)
    return ((vals.get("APIFY_TOKEN") or vals.get("APIFY_API_TOKEN") or "") if vals else "").strip()


def apify_disponivel() -> bool:
    return bool(_api_token())


def chave_consulta(cidade: str, tipo: Optional[str]) -> str:
    return f"{_fold(cidade)}|{(tipo or 'imovel').lower()}|venda"


def _slug(cidade: str) -> str:
    return RE_SLUG.sub("-", _fold(cidade)).strip("-")


def _uf(cnj: Optional[str]) -> Optional[str]:
    alias = tribunal_alias(cnj or "")
    if not alias:
        return None
    return UF_TRIBUNAL.get(alias)


def location_input(cidade: str, tipo: Optional[str], cnj: Optional[str] = None) -> str:
    """URL de venda no VivaReal quando dá; senão o nome da cidade."""
    uf = _uf(cnj)
    slug = _slug(cidade)
    path = TIPO_PATH.get((tipo or "").lower())
    if uf and path:
        return f"https://www.vivareal.com.br/venda/{uf}/{slug}/{path}/"
    if uf:
        return f"https://www.vivareal.com.br/venda/{uf}/{slug}/"
    return cidade.strip()


def locations_to_try(cidade: str, tipo: Optional[str], cnj: Optional[str] = None) -> list[str]:
    seen: list[str] = []
    for loc in (
        location_input(cidade, tipo, cnj),
        location_input(cidade, None, cnj),
        cidade.strip(),
    ):
        if loc and loc not in seen:
            seen.append(loc)
    return seen


def _as_items(data: Any) -> Optional[list]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "data"):
            val = data.get(key)
            if isinstance(val, list):
                return val
    return None


def _preco(item: dict[str, Any]) -> Optional[float]:
    raw = item.get("price")
    if isinstance(raw, dict):
        raw = raw.get("value") or raw.get("amount") or raw.get("preco")
    if isinstance(raw, (int, float)) and raw > 0:
        return float(raw)
    if isinstance(raw, str):
        return _area_m2(raw)
    return None


def _area_anuncio(item: dict[str, Any], tipo: Optional[str]) -> Optional[float]:
    keys = ("totalArea", "total_area", "usableArea", "usable_area", "area")
    if (tipo or "").lower() != "terreno":
        keys = ("usableArea", "usable_area", "totalArea", "total_area", "area")
    for key in keys:
        val = item.get(key)
        if isinstance(val, dict):
            val = val.get("value") or val.get("area")
        num = _area_m2(val if isinstance(val, (str, int, float)) else None)
        if num and num >= 15:
            return num
    return None


def _eh_venda(item: dict[str, Any]) -> bool:
    kind = str(item.get("listingType") or item.get("business") or item.get("tipo") or "")
    low = kind.lower()
    if not low:
        return True
    if "rent" in low or "alug" in low:
        return False
    return "sale" in low or "venda" in low or low in ("sell",)


def ppm2_dos_anuncios(items: list, tipo: Optional[str] = None) -> list[float]:
    out: list[float] = []
    for item in items:
        if not isinstance(item, dict) or not _eh_venda(item):
            continue
        preco = _preco(item)
        area = _area_anuncio(item, tipo)
        if not preco or not area or preco < 20000:
            continue
        ppm2 = preco / area
        if 80 <= ppm2 <= 80_000:
            out.append(ppm2)
    return out


def mediana(valores: list[float]) -> Optional[float]:
    if len(valores) < MIN_LISTINGS:
        return None
    return round(float(statistics.median(valores)), 2)


def _resultado(items: list, *, chave: str, tipo: Optional[str], area: Optional[Union[str, int, float]]) -> dict[str, Any]:
    ppm2s = ppm2_dos_anuncios(items, tipo)
    out: dict[str, Any] = {"apify_consultado_para": chave, "apify": "ok"}
    mid = mediana(ppm2s)
    if mid is None:
        out["apify"] = "poucos"
        out["valor_m2_n"] = len(ppm2s)
        return out
    area_m2 = _area_m2(area)
    out["valor_m2_regiao"] = mid
    out["valor_m2_fonte"] = "apify"
    out["valor_m2_n"] = len(ppm2s)
    if area_m2:
        out["valor_mercado_estimado"] = round(mid * area_m2, 2)
    return out


def consultar_apify(
    *,
    cidade: Optional[str],
    tipo: Optional[str] = None,
    area: Optional[Union[str, int, float]] = None,
    cnj: Optional[str] = None,
    ja_consultado: Optional[str] = None,
    fetch=None,
) -> dict[str, Any]:
    """Mediana de R$/m² de anúncios de venda. Vazio se faltar token/cidade ou <3 anúncios."""
    if not cidade or not str(cidade).strip():
        return {}
    if (tipo or "").lower() == "veiculo":
        return {}
    chave = chave_consulta(cidade, tipo)
    if ja_consultado == chave:
        return {}
    if fetch is None and not apify_disponivel():
        return {}
    locations = locations_to_try(cidade, tipo, cnj)
    payload = {"location": locations[0], "maxItems": MAX_ITEMS}
    if fetch is not None:
        try:
            items = _as_items(fetch(payload))
        except Exception:
            return {"apify": "indisponivel", "apify_consultado_para": chave}
        if items is None:
            return {"apify": "indisponivel", "apify_consultado_para": chave}
        return _resultado(items, chave=chave, tipo=tipo, area=area)
    last = {"apify": "indisponivel", "apify_consultado_para": chave}
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            for loc in locations:
                r = client.post(
                    APIFY_URL,
                    params={"token": _api_token()},
                    json={"location": loc, "maxItems": MAX_ITEMS},
                )
                if r.status_code >= 400:
                    continue
                items = _as_items(r.json())
                if items is None:
                    continue
                out = _resultado(items, chave=chave, tipo=tipo, area=area)
                if out.get("apify") == "ok":
                    return out
                last = out
    except Exception:
        return last
    return last
