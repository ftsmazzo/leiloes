"""Trechos citáveis da avaliação — de onde saiu cada fato."""
from __future__ import annotations

import re
from typing import Any, Optional

from app.edital import RE_AREA_EDIF, RE_AREA_EDIF_REV, RE_LAUDO
from app.gliner_avaliar import ocupacao_se_afirmada
from app.juridico import (
    RE_CITACAO_EDITAL,
    RE_CITADO_OK,
    RE_MEACAO,
    RE_NAO_CITADO,
    RE_USUFRUTO,
    RE_USUFRUTO_LIVRE,
    _hedged,
    _trecho_around,
)
from app.scoring import RE_DESOCUPADO, RE_OCUPADO

MAX_TRECHOS = 8
RE_PREFIX = re.compile(r"\[(edital|laudo|matricula|penhora)\]", re.I)


def _origem_no_blob(blob: str, pos: int, stored_docs: Optional[list] = None) -> str:
    found = None
    for match in RE_PREFIX.finditer(blob[: pos + 1]):
        found = match.group(1).lower()
    tipo = found or "edital"
    for doc in reversed(stored_docs or []):
        if not isinstance(doc, dict) or doc.get("tipo") != tipo:
            continue
        if doc.get("ocr"):
            return "ocr"
        if doc.get("anexo"):
            return "anexo"
        return tipo
    return tipo


def _doc_meta(stored_docs: Optional[list], tipo: str, origem: str) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    for doc in reversed(stored_docs or []):
        if not isinstance(doc, dict):
            continue
        mesmo_tipo = doc.get("tipo") == tipo
        ocr_deste = bool(doc.get("ocr")) and (mesmo_tipo or origem == "ocr")
        if origem == "ocr" and ocr_deste:
            if doc.get("label"):
                meta["peca"] = str(doc["label"])
            meta["ocr"] = True
            if doc.get("paginas") or doc.get("pagina"):
                meta["pagina"] = doc.get("paginas") or doc.get("pagina")
            return meta
        if mesmo_tipo:
            if doc.get("label"):
                meta["peca"] = str(doc["label"])
            if doc.get("ocr"):
                meta["ocr"] = True
            if doc.get("paginas") or doc.get("pagina"):
                meta["pagina"] = doc.get("paginas") or doc.get("pagina")
            return meta
    if origem == "ocr":
        meta["ocr"] = True
    return meta


def _item(
    tipo: str,
    texto: str,
    origem: str,
    *,
    stored_docs: Optional[list] = None,
    peca_tipo: Optional[str] = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {"tipo": tipo, "texto": texto.strip()[:220], "origem": origem}
    out.update(_doc_meta(stored_docs, peca_tipo or tipo, origem))
    return out


def _secoes_blob(blob: str) -> list[tuple[str, str, int]]:
    """[(tipo, texto_da_secao, posicao_no_blob), ...]"""
    matches = list(RE_PREFIX.finditer(blob or ""))
    if not matches:
        return []
    out: list[tuple[str, str, int]] = []
    for i, match in enumerate(matches):
        fim = matches[i + 1].start() if i + 1 < len(matches) else len(blob)
        out.append((match.group(1).lower(), blob[match.end() : fim], match.end()))
    return out


def _pick(
    tipo: str,
    pattern: re.Pattern[str],
    page_text: str,
    blob: str,
    stored_docs: Optional[list] = None,
    *,
    skip_if=None,
    prefer_tipos: Optional[tuple[str, ...]] = None,
) -> Optional[dict[str, str]]:
    if prefer_tipos:
        for want in prefer_tipos:
            for peca_tipo, secao, base in _secoes_blob(blob or ""):
                if peca_tipo != want:
                    continue
                match = pattern.search(secao)
                if not match:
                    continue
                if skip_if and skip_if(secao, match):
                    continue
                fonte = _origem_no_blob(blob, base + match.start(), stored_docs)
                return _item(
                    tipo,
                    _trecho_around(secao, match),
                    fonte,
                    stored_docs=stored_docs,
                    peca_tipo=peca_tipo,
                )
    ordem = (("pdf", blob or ""), ("pagina", page_text or "")) if prefer_tipos else (
        ("pagina", page_text or ""),
        ("pdf", blob or ""),
    )
    for origem, text in ordem:
        match = pattern.search(text)
        if not match:
            continue
        if skip_if and skip_if(text, match):
            continue
        fonte = origem if origem == "pagina" else _origem_no_blob(blob, match.start(), stored_docs)
        peca_tipo = tipo
        if fonte != "pagina":
            found = None
            for prefix in RE_PREFIX.finditer(text[: match.start() + 1]):
                found = prefix.group(1).lower()
            if found:
                peca_tipo = found
        return _item(
            tipo,
            _trecho_around(text, match),
            fonte,
            stored_docs=stored_docs,
            peca_tipo=peca_tipo,
        )
    return None


def _skip_ocupado_hedge(text: str, match: re.Match[str]) -> bool:
    span = text[max(0, match.start() - 80) : match.end() + 40]
    return ocupacao_se_afirmada(span, "ocupado") is None


def _skip_usufruto_hedge(text: str, match: re.Match[str]) -> bool:
    if RE_USUFRUTO_LIVRE.search(text):
        return True
    return _hedged(text, match)


def _trecho_hedge(texto: str, tipo: str) -> bool:
    if tipo == "ocupacao":
        return ocupacao_se_afirmada(texto, "ocupado") is None and bool(re.search(r"ocupad", texto, re.I))
    if tipo == "usufruto":
        return bool(re.search(r"eventual", texto, re.I))
    return False


def coletar_trechos(
    *,
    page_text: str = "",
    blob: str = "",
    riscos: Optional[dict[str, Any]] = None,
    valor_causa: Optional[float] = None,
    peticoes: Optional[list] = None,
    stored_docs: Optional[list] = None,
) -> list[dict[str, str]]:
    """Um trecho por fato. Sem trecho, a UI não afirma o fato."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(item: Optional[dict[str, str]]) -> None:
        if not item or not item.get("texto") or item["tipo"] in seen:
            return
        seen.add(item["tipo"])
        out.append(item)

    add(_pick("ocupacao", RE_DESOCUPADO, page_text, blob, stored_docs))
    if "ocupacao" not in seen:
        add(
            _pick(
                "ocupacao",
                RE_OCUPADO,
                page_text,
                blob,
                stored_docs,
                skip_if=_skip_ocupado_hedge,
            )
        )
    add(_pick("avaliacao", RE_LAUDO, page_text, blob, stored_docs, prefer_tipos=("laudo", "matricula")))
    add(_pick("area", RE_AREA_EDIF, page_text, blob, stored_docs, prefer_tipos=("matricula", "laudo")))
    if "area" not in seen:
        add(
            _pick(
                "area",
                RE_AREA_EDIF_REV,
                page_text,
                blob,
                stored_docs,
                prefer_tipos=("matricula", "laudo"),
            )
        )
    add(_pick("citacao", RE_NAO_CITADO, page_text, blob, stored_docs))
    if "citacao" not in seen:
        add(_pick("citacao", RE_CITADO_OK, page_text, blob, stored_docs))
    if "citacao" not in seen:
        add(_pick("citacao", RE_CITACAO_EDITAL, page_text, blob, stored_docs))
    add(_pick("meacao", RE_MEACAO, page_text, blob, stored_docs))
    add(
        _pick(
            "usufruto",
            RE_USUFRUTO,
            page_text,
            blob,
            stored_docs,
            skip_if=_skip_usufruto_hedge,
        )
    )

    riscos = riscos if isinstance(riscos, dict) else {}
    if "meacao" not in seen and isinstance(riscos.get("meacao_trecho"), str):
        add(_item("meacao", riscos["meacao_trecho"], "edital", stored_docs=stored_docs))
    if "usufruto" not in seen and isinstance(riscos.get("usufruto_trecho"), str):
        if not _trecho_hedge(riscos["usufruto_trecho"], "usufruto"):
            add(_item("usufruto", riscos["usufruto_trecho"], "edital", stored_docs=stored_docs))

    if isinstance(valor_causa, (int, float)) and valor_causa > 0:
        money = f"{valor_causa:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        add(
            _item(
                "valor_causa",
                f"Valor da causa R$ {money} (dívida original, não é o valor do imóvel).",
                "infosimples",
            )
        )
    if isinstance(peticoes, list) and peticoes:
        partes = []
        for p in peticoes[-3:]:
            if not isinstance(p, dict) or not p.get("tipo"):
                continue
            partes.append(" ".join(x for x in (str(p.get("tipo")), str(p.get("data") or "")) if x).strip())
        if partes:
            add(_item("peticao", "; ".join(partes), "infosimples"))

    return out[:MAX_TRECHOS]
