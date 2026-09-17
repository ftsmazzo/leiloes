"""
Orquestrador da avaliação sob demanda.

Ordem fixa — não pontuar com dado de etapa posterior, não deixar o PDF
barato sobrescrever o Valor atual da página:

  1. Página pública  → preços da praça ativa (Valor atual / Valor de avaliação)
  2. PDFs públicos   → fatos jurídicos; NÃO sobrescrevem preço da página
  3. DataJud         → citação só com evidência
  4. Score           → um snapshot de preço (praça ativa vs avaliação)
  5. Parecer         → só fatos do snapshot; sem IA se docs limitados
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

from bs4 import BeautifulSoup

from app import edital
from app.datajud import consultar_datajud, merge_riscos
from app.scrapers.extract import leilao_status, tipo_from_text
from app.scoring import compute_score

CAMPOS_PDF = (
    "avaliacao_edital",
    "avaliacao_fonte",
    "valor_venal_imovel",
    "valor_venal_terreno",
    "valor_venal_edificacao",
    "area_edificacao",
    "area_terreno",
    "area",
    "avaliacao_data",
    "avaliacao_data_origem",
    "processo_cnj",
)


def snapshot_preco(
    page: dict[str, Any],
    extracted: dict[str, Any],
    current_bid: Optional[float],
    minimum_bid: Optional[float],
    reference_value: Optional[float],
) -> dict[str, Any]:
    """Um único recorte de preço. Página da praça ativa ganha de scrape e PDF."""
    lance_pagina = page.get("lance_pagina")
    aval_pagina = page.get("avaliacao_pagina")
    aval_pdf = extracted.get("avaliacao_edital")
    lance = lance_pagina or current_bid
    # Se a página tem Valor atual, esse é o lance da praça — não o mínimo da 1ª.
    inicial = lance_pagina or minimum_bid
    if isinstance(aval_pagina, (int, float)) and aval_pagina > 0:
        avaliacao, fonte = aval_pagina, "pagina"
    elif isinstance(aval_pdf, (int, float)) and aval_pdf > 0:
        avaliacao, fonte = aval_pdf, "pdf"
    elif isinstance(reference_value, (int, float)) and reference_value > 0:
        avaliacao, fonte = reference_value, "scrape"
    else:
        avaliacao, fonte = None, "nenhuma"
    return {
        "lance": lance if isinstance(lance, (int, float)) and lance > 0 else None,
        "inicial": inicial if isinstance(inicial, (int, float)) and inicial > 0 else None,
        "avaliacao": avaliacao,
        "fonte": fonte,
        "lance_pagina": lance_pagina,
        "avaliacao_pagina": aval_pagina,
    }


def _tem_peca_util(docs: list[dict[str, Any]]) -> bool:
    return any(
        isinstance(d, dict)
        and d.get("tipo") in ("laudo", "matricula", "penhora")
        and int(d.get("chars") or 0) >= 80
        and not d.get("scanned")
        for d in docs
    )


def _ler_pdfs(html: str, url: str, fetch_file) -> tuple[list[dict[str, Any]], str, bool]:
    docs = edital.collect_pdfs(html, url)
    texts: list[str] = []
    scanned_any = False
    stored: list[dict[str, Any]] = []
    for doc in docs:
        item = dict(doc)
        try:
            data = fetch_file(doc["url"])
            text, scanned = edital.extract_pdf_text(data)
        except Exception:
            text, scanned = "", True
        if scanned:
            scanned_any = True
            item["scanned"] = True
        item["chars"] = len(text)
        stored.append(item)
        if text:
            texts.append(f"[{doc['tipo']}] {text}")
    return stored, "\n".join(texts), scanned_any


def avaliar(
    *,
    title: str,
    description: Optional[str],
    url: str,
    current_bid: Optional[float],
    minimum_bid: Optional[float],
    reference_value: Optional[float],
    extra: dict[str, Any],
    fetch_page=None,
    fetch_file=None,
    fetch_datajud=None,
    write_ai: bool = True,
) -> dict[str, Any]:
    fetch_page = fetch_page or edital.fetch_html
    fetch_file = fetch_file or edital.fetch_pdf

    html = fetch_page(url)
    page_text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    status = leilao_status(title, description, page_text[:4000])

    # 1. Página — preços da praça ativa
    page_precos = edital.precos_from_page(page_text, html=html)

    # 2. PDFs públicos — fatos, não preço
    stored_docs, blob, scanned_any = _ler_pdfs(html, url, fetch_file)
    extracted = edital.fields_from_text(
        blob,
        page_text[:8000],
        source=str(extra.get("source") or ""),
    )
    snap = snapshot_preco(
        page_precos, extracted, current_bid, minimum_bid, reference_value
    )

    out = dict(extra)
    out["docs"] = stored_docs
    out["avaliado_em"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out["status"] = status
    out["preco_fonte"] = snap["fonte"]
    for key in CAMPOS_PDF:
        if extracted.get(key) not in (None, "", [], {}):
            out[key] = extracted[key]
    if extracted.get("ocupacao"):
        out["ocupacao"] = extracted["ocupacao"]
    if extracted.get("dividas"):
        out["dividas"] = extracted["dividas"]
    if stored_docs and not blob.strip():
        out["edital_sem_texto"] = True
    if snap["lance_pagina"]:
        out["lance_pagina"] = snap["lance_pagina"]
    if snap["avaliacao_pagina"]:
        out["avaliacao_pagina"] = snap["avaliacao_pagina"]
        out["avaliacao_edital"] = snap["avaliacao_pagina"]
        if not out.get("avaliacao_fonte"):
            out["avaliacao_fonte"] = "laudo"

    # 3. DataJud — citação só com evidência
    riscos = dict(extracted.get("riscos") or {})
    cnj = riscos.get("processo_cnj")
    if isinstance(cnj, str) and cnj:
        dj = consultar_datajud(cnj, fetch=fetch_datajud)
        riscos = merge_riscos(riscos, dj)
    docs_limitados = not _tem_peca_util(stored_docs)
    if docs_limitados:
        out["docs_limitados"] = True
        riscos["docs_limitados"] = True
    if riscos:
        out["riscos"] = riscos
        if riscos.get("processo_cnj"):
            out["processo_cnj"] = riscos["processo_cnj"]
        if riscos.get("nao_entrar"):
            out["nao_entrar"] = True
        else:
            out.pop("nao_entrar", None)

    tipo = out.get("tipo") if isinstance(out.get("tipo"), str) else None
    tipo = tipo or tipo_from_text(title, description)
    if tipo:
        out["tipo"] = tipo

    # Sem peca útil: não pontuar ocupação/condomínio inventados do edital curto
    ocupacao = out.get("ocupacao") if isinstance(out.get("ocupacao"), str) else None
    tem_divida = extracted.get("tem_divida") if isinstance(extracted.get("tem_divida"), bool) else None
    dividas = out.get("dividas") if isinstance(out.get("dividas"), dict) else None
    if docs_limitados:
        ocupacao_score, tem_divida_score = None, None
        dividas_score = dividas if dividas and dividas.get("condominio") else None
    else:
        ocupacao_score, tem_divida_score, dividas_score = ocupacao, tem_divida, dividas

    fonte = out.get("avaliacao_fonte") if out.get("avaliacao_fonte") in ("laudo", "venal_imovel") else None
    desc = " ".join(p for p in (description, page_text[:4000], blob[:3000]) if p)

    # 4. Score — snapshot único (praça ativa vs avaliação da página)
    score_info = compute_score(
        title=title,
        description=desc,
        current_bid=snap["lance"],
        minimum_bid=snap["inicial"],
        reference_value=snap["avaliacao"],
        valor_mercado_estimado=out.get("valor_mercado_estimado")
        if isinstance(out.get("valor_mercado_estimado"), (int, float))
        else None,
        ocupacao=ocupacao_score,
        tem_divida=tem_divida_score,
        fonte_avaliacao=fonte,
        dividas=dividas_score,
        avaliacao_data=out.get("avaliacao_data"),
        avaliacao_data_origem=out.get("avaliacao_data_origem")
        if out.get("avaliacao_data_origem") in ("laudo", "processo")
        else None,
        tipo=tipo,
        riscos=riscos or None,
    )
    out["score"] = score_info["score"]
    out["score_tem_comparacao_preco"] = score_info["tem_comparacao_preco"]
    out["score_motivos"] = score_info["motivos"]

    facts = {
        "score": out["score"],
        "tem_comparacao_preco": out["score_tem_comparacao_preco"],
        "motivos": out["score_motivos"],
        "avaliacao_edital": out.get("avaliacao_edital"),
        "avaliacao_fonte": out.get("avaliacao_fonte"),
        "valor_venal_terreno": out.get("valor_venal_terreno"),
        "valor_venal_imovel": out.get("valor_venal_imovel"),
        "area_edificacao": out.get("area_edificacao"),
        "area_terreno": out.get("area_terreno"),
        "avaliacao_data": out.get("avaliacao_data"),
        "avaliacao_data_origem": out.get("avaliacao_data_origem"),
        "lance_atual": snap["lance"] if snap["lance"] is not None else snap["inicial"],
        "status": status,
        "ocupacao": ocupacao if not docs_limitados else None,
        "dividas": out.get("dividas"),
        "docs": stored_docs,
        "scanned": scanned_any,
        "docs_limitados": docs_limitados,
        "cidade": out.get("cidade"),
        "headline": out.get("headline"),
        "processo_cnj": out.get("processo_cnj"),
        "riscos": riscos or None,
        "nao_entrar": bool(out.get("nao_entrar")),
    }

    # 5. Parecer — sem IA se a leitura foi só edital/página
    analise_limitada = bool(docs_limitados or out.get("edital_sem_texto") or scanned_any)
    parecer = edital._mistral_parecer(facts) if write_ai and not analise_limitada else None
    if parecer and status != "encerrado" and re.search(r"\barrematad", parecer, re.I):
        parecer = None
    if parecer and not out.get("nao_entrar") and re.search(r"n[aã]o entre", parecer, re.I):
        parecer = None
    out["parecer"] = parecer or edital.parecer_from_facts(facts)
    return {k: v for k, v in out.items() if v not in (None, "", [], {})}
