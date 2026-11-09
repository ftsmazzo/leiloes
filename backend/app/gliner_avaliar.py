"""GLiNER na avaliação: preenche o que o regex não achou. Não inventa fato hedged."""
from __future__ import annotations

import re
from typing import Any, Optional

from app.juridico import RE_CNJ, RE_HEDGE, RE_USUFRUTO_LIVRE, _hedged, format_cnj
from app.scrapers.extract import gliner_configured, gliner_entities, parse_br_currency
from app.scrapers.soleon import _ocupacao_of
from app.scoring import RE_DESOCUPADO, RE_OCUPADO

MAX_CHARS = 8000
RE_HEDGE_OCUP = re.compile(
    r"caso\s+(?:o\s+)?im[oó]vel\s+esteja|caso\s+esteja\s+ocupad|"
    r"se\s+(?:o\s+)?im[oó]vel\s+estiver|se\s+houver|hip[oó]tese|eventual",
    re.I,
)

GLINER_AVALIAR_LABELS = {
    "ocupacao": "imovel desocupado ou ocupado, se afirmado de fato neste bem",
    "onus": "usufruto ou onus real existente neste imovel",
    "meacao": "penhora da meacao ou venda de apenas metade do imovel",
    "divida": "debito de iptu ou condominio com valor em reais",
    "cnj": "numero CNJ do processo judicial",
    "citacao": "executado citado, nao citado ou citacao por edital",
    "avaliacao": "valor do laudo de avaliacao judicial em reais",
    "area": "area privativa ou construida em metros quadrados",
    "matricula": "numero da matricula do imovel",
}


def _span_hedged(text: str, span: str) -> bool:
    blob = f"{text} {span}"
    if RE_HEDGE.search(span) or RE_HEDGE_OCUP.search(span):
        return True
    pos = blob.lower().find(str(span).lower())
    if pos < 0:
        return bool(RE_HEDGE_OCUP.search(text[-80:] if len(text) > 80 else text))
    window = blob[max(0, pos - 60) : pos + len(span)]
    return bool(RE_HEDGE.search(window) or RE_HEDGE_OCUP.search(window))


def ocupacao_se_afirmada(text: str, ocupacao: Optional[str]) -> Optional[str]:
    """«Caso o imóvel esteja ocupado» não é ocupação afirmada."""
    if ocupacao != "ocupado":
        return ocupacao
    if RE_DESOCUPADO.search(text or ""):
        return "desocupado"
    matches = list(RE_OCUPADO.finditer(text or ""))
    if not matches:
        return ocupacao
    if all(_hedged(text, m) or RE_HEDGE_OCUP.search((text or "")[max(0, m.start() - 60) : m.end()]) for m in matches):
        return None
    return "ocupado"


def fatos_gliner(text: str, *, fetch=None) -> dict[str, Any]:
    """Só devolve campo que o modelo citou. Sem GLiNER configurado, vazio."""
    if fetch is None and not gliner_configured():
        return {}
    mix = (text or "").strip()[:MAX_CHARS]
    if not mix:
        return {}
    ents = gliner_entities(mix, labels=GLINER_AVALIAR_LABELS, fetch=fetch)
    out: dict[str, Any] = {}
    for span in ents.get("ocupacao") or []:
        if _span_hedged(mix, span):
            continue
        occ = _ocupacao_of(span)
        if occ:
            out["ocupacao"] = occ
            break
    for span in ents.get("cnj") or []:
        found = RE_CNJ.search(span)
        digits = re.sub(r"\D", "", span)
        if found:
            out["processo_cnj"] = format_cnj(found.group(1))
            break
        if len(digits) == 20:
            out["processo_cnj"] = format_cnj(digits)
            break
    for span in ents.get("area") or []:
        if re.search(r"\d", span):
            out["area"] = re.sub(r"\s+", " ", span).strip()[:40]
            break
    for span in ents.get("matricula") or []:
        clip = re.sub(r"\s+", " ", span).strip()[:40]
        if clip:
            out["matricula"] = clip
            break
    for span in ents.get("avaliacao") or []:
        money = parse_br_currency(span)
        if money and money > 1000:
            out["avaliacao_edital"] = money
            out["avaliacao_fonte"] = "laudo"
            break
    dividas: dict[str, Any] = {}
    for span in ents.get("divida") or []:
        money = parse_br_currency(span)
        if not money or money <= 0:
            continue
        low = span.lower()
        if "iptu" in low:
            dividas.setdefault("iptu", money)
        elif "condom" in low:
            dividas.setdefault("condominio", money)
    if dividas:
        out["dividas"] = dividas
    riscos: dict[str, Any] = {}
    if not RE_USUFRUTO_LIVRE.search(mix):
        for span in ents.get("onus") or []:
            if _span_hedged(mix, span):
                continue
            if re.search(r"usufrut|uso\s+e\s+fruto", span, re.I):
                riscos["usufruto"] = True
                riscos["usufruto_trecho"] = re.sub(r"\s+", " ", span).strip()[:180]
                break
    for span in ents.get("meacao") or []:
        if _span_hedged(mix, span):
            continue
        if re.search(r"mea[cç][aã]o|metade\s+d[oa]", span, re.I):
            riscos["meacao"] = True
            riscos["meacao_trecho"] = re.sub(r"\s+", " ", span).strip()[:180]
            break
    for span in ents.get("citacao") or []:
        if _span_hedged(mix, span):
            continue
        low = span.lower()
        if re.search(r"n[aã]o\s+(?:foi\s+)?citad|sem\s+cita", low):
            riscos["citacao"] = "nao_citado"
            riscos["nao_entrar"] = True
            break
        if re.search(r"cita[cç][aã]o\s+por\s+edital", low):
            riscos["citacao"] = "edital"
            break
        if re.search(r"citad", low):
            riscos["citacao"] = "citado"
            break
    if riscos:
        out["riscos"] = riscos
    if out:
        out["extract_avaliar"] = "gliner"
    return out


def mesclar_gliner(dst: dict[str, Any], riscos: dict[str, Any], gli: dict[str, Any]) -> None:
    """Regex/HTML já no dst ganham. GLiNER só preenche furo."""
    if gli.get("ocupacao") and not dst.get("ocupacao"):
        dst["ocupacao"] = gli["ocupacao"]
    for key in ("area", "matricula", "avaliacao_edital", "avaliacao_fonte", "processo_cnj"):
        if gli.get(key) and not dst.get(key):
            dst[key] = gli[key]
    if isinstance(gli.get("dividas"), dict):
        dividas = dict(dst.get("dividas") or {})
        for key, val in gli["dividas"].items():
            dividas.setdefault(key, val)
        if dividas:
            dst["dividas"] = dividas
    extra_r = gli.get("riscos") if isinstance(gli.get("riscos"), dict) else {}
    if extra_r.get("processo_cnj") and not riscos.get("processo_cnj"):
        riscos["processo_cnj"] = extra_r["processo_cnj"]
    if extra_r.get("usufruto") and not riscos.get("usufruto"):
        riscos["usufruto"] = True
        if extra_r.get("usufruto_trecho"):
            riscos["usufruto_trecho"] = extra_r["usufruto_trecho"]
    if extra_r.get("meacao") and not riscos.get("meacao"):
        riscos["meacao"] = True
        if extra_r.get("meacao_trecho"):
            riscos["meacao_trecho"] = extra_r["meacao_trecho"]
    if extra_r.get("citacao") and not riscos.get("citacao"):
        riscos["citacao"] = extra_r["citacao"]
        if extra_r.get("nao_entrar"):
            riscos["nao_entrar"] = True
    if gli.get("processo_cnj") and not riscos.get("processo_cnj"):
        riscos["processo_cnj"] = gli["processo_cnj"]
    if gli.get("extract_avaliar"):
        dst["extract_avaliar"] = gli["extract_avaliar"]
