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
    r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç'.-]{2,40}"
    r"(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç'.-]{1,30}){0,6})",
    re.I,
)
RE_LIXO_NOME = re.compile(
    r"^(nao|n[aã]o|deve|poder|sera|estar|fica|declar|responsab|"
    r"nomead|designad|comprom|observ|inform|garant)",
    re.I,
)
CASAS = (
    ("calil", re.compile(r"calil", re.I)),
    ("zuk", re.compile(r"\bzuk\b", re.I)),
    ("vegas", re.compile(r"vegas\s*leil", re.I)),
    ("mega", re.compile(r"mega\s*leil", re.I)),
    ("lance", re.compile(r"grupo\s*lance|\blance\s*leil", re.I)),
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
    r"penhora\s+da\s+mea[cç][aã]o|"
    r"mea[cç][aã]o\s+(?:do\s+executado|do\s+im[oó]vel|da\s+propriedade)|"
    r"(?:leil[aã]o|aliena[cç][aã]o|hasta|venda)\s+d[ae]\s+mea[cç][aã]o|"
    r"apenas\s+(?:a\s+)?mea[cç][aã]o|"
    r"(?:50|50,00)\s*%.{0,20}(?:do\s+im[oó]vel|da\s+propriedade)|"
    r"apenas\s+(?:a\s+)?metade\s+(?:do\s+im[oó]vel|da\s+propriedade)",
    re.I,
)


def _fold(text: str) -> str:
    norm = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in norm if unicodedata.category(ch) != "Mn").lower()


def _casas_of(text: str, source: str = "") -> set[str]:
    blob = f"{text} {source}"
    found = {casa for casa, pat in CASAS if pat.search(blob)}
    src = _fold(source).strip()
    if src in {casa for casa, _ in CASAS}:
        found.add(src)
    return found


def _norm_nome(text: str) -> str:
    text = re.sub(
        r"\b(oficial|leiloeiro|publico|p[uú]blico|dra?|sr\.?|leiloes|www|https?|ltda|epp)\b",
        " ",
        _fold(text),
        flags=re.I,
    )
    return re.sub(r"[^a-z]+", "", text)


def _tokens_nome(text: str) -> set[str]:
    folded = _fold(text)
    stop = {
        "oficial", "leiloeiro", "publico", "leiloes", "www", "com", "br",
        "ltda", "epp", "assessoria", "empresa", "site", "https", "http",
    }
    return {tok for tok in re.findall(r"[a-z]{4,}", folded) if tok not in stop}


def _limpa_nome(raw: str) -> Optional[str]:
    nome = re.sub(r"\s+", " ", raw).strip(" ,.;:-")
    nome = re.split(
        r"\s+-\s+|\s+inscrit|\s+junta|\s+creci|\s+matr[ií]cula|\n",
        nome,
        maxsplit=1,
        flags=re.I,
    )[0].strip(" ,.;")
    if len(nome) < 4 or RE_LIXO_NOME.search(nome):
        return None
    return nome[:80]


def format_cnj(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) != 20:
        return raw.strip()
    return f"{digits[0:7]}-{digits[7:9]}.{digits[9:13]}.{digits[13]}.{digits[14:16]}.{digits[16:20]}"


def _leiloeiros_of(blob: str) -> list[str]:
    seen: list[str] = []
    for found in RE_LEILOEIRO.finditer(blob or ""):
        nome = _limpa_nome(found.group(1))
        if nome and nome not in seen:
            seen.append(nome)
    return seen


def _nomes_batem(edital: list[str], site: list[str]) -> bool:
    for a in edital:
        na, ta = _norm_nome(a), _tokens_nome(a)
        for b in site:
            nb, tb = _norm_nome(b), _tokens_nome(b)
            if na and nb and (na in nb or nb in na):
                return True
            if ta & tb:
                return True
    return False


def _leiloeiro_ok(blob: str, page_text: str, source: str = "") -> Optional[bool]:
    """True = mesma casa/nome. False = pessoas diferentes. None = não acusa."""
    casas_edital = _casas_of(blob)
    casas_site = _casas_of(page_text, source)
    if casas_edital and casas_site and casas_edital & casas_site:
        return True
    edital = _leiloeiros_of(blob)
    site = _leiloeiros_of(page_text)
    if not edital or not site:
        return None
    if _nomes_batem(edital, site):
        return True
    if _casas_of(" ".join(edital)) & _casas_of(" ".join(site), source):
        return True
    return False


def _trecho_around(text: str, match: re.Match[str], pad: int = 50) -> str:
    start = max(0, match.start() - pad)
    end = min(len(text), match.end() + pad)
    trecho = re.sub(r"\s+", " ", text[start:end]).strip()
    return trecho[:180]


def riscos_from_text(blob: str, page_text: str = "", source: str = "") -> dict[str, Any]:
    """Lê citação, usufruto, meação, CNJ e leiloeiro no texto público."""
    out: dict[str, Any] = {}
    cnj = RE_CNJ.search(blob) or RE_CNJ.search(page_text)
    compact = None if cnj else (RE_CNJ_COMPACT.search(blob) or RE_CNJ_COMPACT.search(page_text))
    if cnj:
        out["processo_cnj"] = format_cnj(cnj.group(1))
    elif compact:
        out["processo_cnj"] = format_cnj(compact.group(1))

    edital_lei = _leiloeiros_of(blob)
    site_lei = _leiloeiros_of(page_text) if page_text else []
    if edital_lei:
        out["leiloeiro_edital"] = edital_lei[0]
    if site_lei:
        out["leiloeiro_site"] = site_lei[0]
    ok = _leiloeiro_ok(blob, page_text, source)
    if ok is not None:
        out["leiloeiro_ok"] = ok

    if RE_NAO_CITADO.search(blob) and not RE_CITADO_OK.search(blob):
        out["citacao"] = "nao_citado"
        out["nao_entrar"] = True
    elif RE_CITACAO_EDITAL.search(blob) and not RE_CITADO_OK.search(blob):
        out["citacao"] = "edital"
    elif RE_CITADO_OK.search(blob):
        out["citacao"] = "citado"

    mix = f"{blob}\n{page_text}"
    if RE_USUFRUTO.search(blob) and not RE_USUFRUTO_LIVRE.search(blob):
        out["usufruto"] = True
        u = RE_USUFRUTO.search(blob)
        if u:
            out["usufruto_trecho"] = _trecho_around(blob, u)
    meacao = RE_MEACAO.search(mix)
    if meacao:
        out["meacao"] = True
        out["meacao_trecho"] = _trecho_around(mix, meacao)
    return out
