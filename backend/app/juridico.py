"""
Riscos jurídicos lidos do edital/matrícula públicos.

Não consulta PJe/e-SAJ (CAPTCHA/login). Só o que o PDF já escreveu.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional

RE_CNJ = re.compile(r"\b(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})\b")
RE_CNJ_COMPACT = re.compile(r"\bprocesso\s*n[ºo°.]?\s*(\d{20})\b", re.I)
RE_LEILOEIRO = re.compile(
    r"leiloeiro(?:\s+p[uú]blico)?(?:\s+oficial)?[:\s,]+"
    r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç'. ]{4,70})",
    re.I,
)
RE_NAO_CITADO = re.compile(
    r"(?:executado|devedor|propriet[aá]rio).{0,50}n[aã]o\s+(?:foi\s+)?citad|"
    r"n[aã]o\s+(?:foi\s+)?citad.{0,40}(?:executado|devedor)|"
    r"sem\s+cita[cç][aã]o|"
    r"cita[cç][aã]o\s+pendente|"
    r"aguarda(?:ndo)?\s+cita[cç][aã]o",
    re.I,
)
RE_CITADO_OK = re.compile(
    r"(?:regularmente|pessoalmente)\s+citad|"
    r"cita[cç][aã]o\s+pessoal|"
    r"executado\s+(?:foi\s+)?citad",
    re.I,
)
RE_CITACAO_EDITAL = re.compile(r"cita[cç][aã]o\s+por\s+edital", re.I)
RE_USUFRUTO = re.compile(r"\busufrut|\buso\s+e\s+fruto", re.I)
RE_USUFRUTO_LIVRE = re.compile(
    r"(?:sem|livre\s+de|inexist|n[aã]o\s+h[aá]).{0,25}(?:usufrut|uso\s+e\s+fruto)|"
    r"(?:usufrut|uso\s+e\s+fruto).{0,30}(?:cancel|extint|baix|inexist)",
    re.I,
)
RE_MEACAO = re.compile(
    r"\bmea[cç][aã]o\b|"
    r"fra[cç][aã]o\s+ideal|"
    r"parte\s+ideal|"
    r"copropriedade|"
    r"(?:50|50,00)\s*%.{0,25}(?:do\s+im[oó]vel|da\s+propriedade)|"
    r"apenas\s+(?:a\s+)?metade",
    re.I,
)
RE_CONJUGE_BEM = re.compile(
    r"c[oô]njuge\s+do\s+executado|"
    r"executado\s+e\s+(?:sua\s+)?c[oô]njuge|"
    r"bem\s+de\s+fam[ií]lia|"
    r"comunh[aã]o\s+(?:parcial|universal)",
    re.I,
)
RE_CONJUGE_ARREMATANTE = re.compile(r"c[oô]njuge\s+do\s+arrematante", re.I)


def _fold(text: str) -> str:
    norm = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in norm if unicodedata.category(ch) != "Mn").lower()


def _norm_nome(text: str) -> str:
    text = re.sub(r"\b(oficial|leiloeiro|publico|p[uú]blico|dra?|sr\.?)\b", " ", _fold(text), flags=re.I)
    return re.sub(r"[^a-z]+", "", text)


def format_cnj(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) != 20:
        return raw.strip()
    return f"{digits[0:7]}-{digits[7:9]}.{digits[9:13]}.{digits[13]}.{digits[14:16]}.{digits[16:20]}"


def _leiloeiro_of(blob: str) -> Optional[str]:
    found = RE_LEILOEIRO.search(blob)
    if not found:
        return None
    nome = re.sub(r"\s+", " ", found.group(1)).strip(" ,.;")
    nome = re.split(r"\s+-\s+|\s+inscrit", nome, maxsplit=1)[0].strip()
    return nome[:80] if len(nome) >= 5 else None


def riscos_from_text(blob: str, page_text: str = "") -> dict[str, Any]:
    """Lê citação, usufruto, meação, CNJ e leiloeiro no texto público."""
    out: dict[str, Any] = {}
    cnj = RE_CNJ.search(blob) or RE_CNJ.search(page_text)
    compact = None if cnj else (RE_CNJ_COMPACT.search(blob) or RE_CNJ_COMPACT.search(page_text))
    if cnj:
        out["processo_cnj"] = format_cnj(cnj.group(1))
    elif compact:
        out["processo_cnj"] = format_cnj(compact.group(1))

    edital_lei = _leiloeiro_of(blob)
    site_lei = _leiloeiro_of(page_text) if page_text else None
    if edital_lei:
        out["leiloeiro_edital"] = edital_lei
    if site_lei:
        out["leiloeiro_site"] = site_lei
    if edital_lei and site_lei:
        a, b = _norm_nome(edital_lei), _norm_nome(site_lei)
        out["leiloeiro_ok"] = bool(a and b and (a in b or b in a))

    if RE_NAO_CITADO.search(blob) and not RE_CITADO_OK.search(blob):
        out["citacao"] = "nao_citado"
        out["nao_entrar"] = True
    elif RE_CITACAO_EDITAL.search(blob) and not RE_CITADO_OK.search(blob):
        out["citacao"] = "edital"
    elif RE_CITADO_OK.search(blob):
        out["citacao"] = "citado"

    if RE_USUFRUTO.search(blob) and not RE_USUFRUTO_LIVRE.search(blob):
        out["usufruto"] = True
    meacao = bool(RE_MEACAO.search(blob))
    conjuge = bool(RE_CONJUGE_BEM.search(blob))
    so_arrematante = bool(RE_CONJUGE_ARREMATANTE.search(blob)) and not conjuge
    if (meacao or conjuge) and not so_arrematante:
        out["meacao"] = True
    return out
