"""
Consulta pública DataJud (CNJ) pelo número do processo.

Não abre PJe/e-SAJ. Só metadados: classe, ajuizamento, movimentos TPU.
A chave da wiki é pública e pode girar — override em DATAJUD_API_KEY.
CI não bate na API: os testes injetam a resposta.
"""
from __future__ import annotations

import os
import re
from typing import Any, Optional

import httpx

from app.juridico import _fold

DATAJUD_BASE = "https://api-publica.datajud.cnj.jus.br"
# Chave pública documentada na wiki do CNJ; não é segredo de usuário.
DATAJUD_PUBLIC_KEY = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="
TIMEOUT = 20.0

# Justiça estadual: dígitos TR do CNJ (NNNNNNN-DD.AAAA.8.TR.OOOO)
ESTADUAL = {
    "01": "tjac",
    "02": "tjal",
    "03": "tjap",
    "04": "tjam",
    "05": "tjba",
    "06": "tjce",
    "07": "tjdft",
    "08": "tjes",
    "09": "tjgo",
    "10": "tjma",
    "11": "tjmt",
    "12": "tjms",
    "13": "tjmg",
    "14": "tjpa",
    "15": "tjpb",
    "16": "tjpr",
    "17": "tjpe",
    "18": "tjpi",
    "19": "tjrj",
    "20": "tjrn",
    "21": "tjrs",
    "22": "tjro",
    "23": "tjrr",
    "24": "tjsc",
    "25": "tjse",
    "26": "tjsp",
    "27": "tjto",
}

RE_CITACAO = re.compile(r"citac", re.I)
RE_EDITAL = re.compile(r"edital", re.I)
RE_NEGATIVA = re.compile(r"negativ|infrut|n[aã]o\s+(?:efetiv|cumpr|realiz)|nao\s+efetu", re.I)
RE_CUMPRIDA = re.compile(r"efetiv|cumpr|positiv|pessoal|realizad", re.I)
RE_EXPEDICAO = re.compile(r"expedic|mandado", re.I)


def cnj_digits(cnj: str) -> str:
    return re.sub(r"\D", "", cnj or "")


def tribunal_alias(cnj: str) -> Optional[str]:
    digits = cnj_digits(cnj)
    if len(digits) != 20:
        return None
    ramo, tr = digits[13], digits[14:16]
    if ramo == "8":
        return ESTADUAL.get(tr)
    if ramo == "4":
        n = int(tr)
        if 1 <= n <= 6:
            return f"trf{n}"
        return None
    if ramo == "5":
        n = int(tr)
        if 1 <= n <= 24:
            return f"trt{n}"
        return None
    return None


def citacao_from_movimentos(movimentos: list[Any]) -> Optional[str]:
    """citado | edital | pendente | nao_citado | None (sem evidência)."""
    cit = []
    for item in movimentos:
        if isinstance(item, dict) and item.get("nome"):
            nome = _fold(str(item["nome"]))
            if RE_CITACAO.search(nome):
                cit.append(nome)
    if not cit:
        return None
    if any(RE_NEGATIVA.search(n) for n in cit):
        return "nao_citado"
    if any(RE_CUMPRIDA.search(n) and not RE_EDITAL.search(n) for n in cit):
        return "citado"
    if any(RE_EDITAL.search(n) for n in cit):
        return "edital"
    if any(RE_EXPEDICAO.search(n) for n in cit):
        return "pendente"
    return "pendente"


def _api_key() -> str:
    return os.getenv("DATAJUD_API_KEY", "").strip() or DATAJUD_PUBLIC_KEY


def consultar_datajud(
    cnj: str,
    *,
    fetch=None,
) -> dict[str, Any]:
    """Devolve recorte do processo. Vazio se falhar ou não achar. Sem rede no CI."""
    alias = tribunal_alias(cnj)
    digits = cnj_digits(cnj)
    if not alias or len(digits) != 20:
        return {}
    url = f"{DATAJUD_BASE}/api_publica_{alias}/_search"
    payload = {
        "size": 1,
        "query": {"match": {"numeroProcesso": digits}},
        "_source": ["numeroProcesso", "classe", "dataAjuizamento", "movimentos", "orgaoJulgador", "tribunal"],
    }
    headers = {
        "Authorization": f"APIKey {_api_key()}",
        "Content-Type": "application/json",
    }
    try:
        if fetch is not None:
            data = fetch(url, payload)
        else:
            with httpx.Client(timeout=TIMEOUT) as client:
                r = client.post(url, headers=headers, json=payload)
                if r.status_code >= 400:
                    return {"datajud": "indisponivel"}
                data = r.json()
    except Exception:
        return {"datajud": "indisponivel"}
    hits = (((data or {}).get("hits") or {}).get("hits")) or []
    if not hits:
        return {"datajud": "nao_encontrado"}
    src = hits[0].get("_source") if isinstance(hits[0], dict) else None
    if not isinstance(src, dict):
        return {"datajud": "nao_encontrado"}
    movs = src.get("movimentos") if isinstance(src.get("movimentos"), list) else []
    citacao = citacao_from_movimentos(movs)
    out: dict[str, Any] = {
        "datajud": "ok",
        "datajud_tribunal": src.get("tribunal") or alias.upper(),
        "datajud_classe": (src.get("classe") or {}).get("nome") if isinstance(src.get("classe"), dict) else None,
        "datajud_ajuizamento": src.get("dataAjuizamento"),
    }
    if citacao:
        out["citacao"] = citacao
        out["citacao_fonte"] = "datajud"
        if citacao in ("nao_citado", "pendente"):
            out["nao_entrar"] = True
    return {k: v for k, v in out.items() if v not in (None, "", [], {})}


def merge_riscos(base: dict[str, Any], datajud: dict[str, Any]) -> dict[str, Any]:
    """DataJud ganha na citação quando traz evidência. PDF continua em usufruto/meação."""
    out = dict(base)
    for key in ("datajud", "datajud_tribunal", "datajud_classe", "datajud_ajuizamento"):
        if datajud.get(key):
            out[key] = datajud[key]
    if datajud.get("citacao"):
        out["citacao"] = datajud["citacao"]
        out["citacao_fonte"] = "datajud"
        if datajud["citacao"] in ("nao_citado", "pendente"):
            out["nao_entrar"] = True
        else:
            out.pop("nao_entrar", None)
    elif out.get("citacao") in ("nao_citado", "pendente"):
        out["nao_entrar"] = True
    return out
