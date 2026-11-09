"""
Orquestrador da avaliação sob demanda.

Ordem fixa — não pontuar com dado de etapa posterior, não deixar o PDF
barato sobrescrever o Valor atual da página:

  1. Página pública  → preços da praça ativa (Valor atual / Valor de avaliação)
  2. PDFs públicos   → fatos jurídicos; NÃO sobrescrevem preço da página
  3. DataJud         → citação só com evidência
  4. Score           → um snapshot de preço (praça ativa vs avaliação)
  5. Parecer         → fatos + trechos + recorte do blob; sem IA só se não houver texto útil
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

from bs4 import BeautifulSoup

from app import edital
from app.apify_mercado import apify_disponivel, chave_consulta, consultar_apify
from app.datajud import consultar_datajud, merge_riscos
from app.infosimples import consultar_infosimples, infosimples_disponivel, merge_infosimples
from app.gliner_avaliar import fatos_gliner, mesclar_gliner, ocupacao_se_afirmada
from app.ocr import ocr_pdf
from app.scrapers.market_price import _area_m2, estimate_market_value
from app.scrapers.extract import leilao_status, tipo_from_text
from app.scrapers.listing import merge_pracas, pracas_from_html
from app.scrapers.soleon import fatos_from_html
from app.scoring import apply_score, compute_score
from app.trechos import coletar_trechos

MAX_ANEXOS = 3

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


def _ler_um(data: bytes, item: dict[str, Any], ocr_fn) -> tuple[dict[str, Any], str, bool]:
    try:
        text, scanned = edital.extract_pdf_text(data)
    except Exception:
        text, scanned = "", True
    tipo = str(item.get("tipo") or "")
    precisa_ocr = scanned or (
        tipo in ("matricula", "laudo") and not edital.peca_nativa_serve(tipo, text)
    )
    paginas = 4 if tipo == "matricula" else 2
    if precisa_ocr and ocr_fn:
        try:
            ocr_text = (ocr_fn(data, max_pages=paginas) or "").strip()
        except TypeError:
            ocr_text = (ocr_fn(data) or "").strip()
        if len(ocr_text) >= 80:
            text, scanned = ocr_text, False
            item["ocr"] = True
            item["paginas"] = paginas
        elif ocr_text:
            text = ocr_text
            item["ocr"] = True
            item["ocr_curto"] = True
            item["confianca"] = "baixa"
            item["trecho"] = ocr_text[:220]
            item["paginas"] = paginas
    if scanned:
        item["scanned"] = True
    item["chars"] = len(text)
    return item, text, scanned


def _ler_anexos_em(
    stored: list[dict[str, Any]],
    texts: list[str],
    anexos: Optional[list[tuple[str, bytes]]],
    ocr_fn,
) -> bool:
    scanned_any = False
    for name, data in (anexos or [])[:MAX_ANEXOS]:
        if not data:
            continue
        tipo = edital.classify_doc(name or "", name or "")
        item = {"tipo": tipo, "label": (name or tipo)[:80], "anexo": True}
        item, text, scanned = _ler_um(data[: edital.MAX_PDF_BYTES], item, ocr_fn)
        if scanned:
            scanned_any = True
        stored.append(item)
        if text:
            texts.append(f"[{tipo}] {text}")
    return scanned_any


def _ler_pdfs(
    html: str,
    url: str,
    fetch_file,
    anexos: Optional[list[tuple[str, bytes]]] = None,
    ocr_fn=None,
) -> tuple[list[dict[str, Any]], str, bool]:
    docs = edital.collect_pdfs(html, url)
    texts: list[str] = []
    scanned_any = False
    stored: list[dict[str, Any]] = []
    for doc in docs:
        item = dict(doc)
        try:
            data = fetch_file(doc["url"])
        except Exception:
            data = b""
        item, text, scanned = _ler_um(data, item, ocr_fn)
        if scanned:
            scanned_any = True
        stored.append(item)
        if text:
            texts.append(f"[{doc['tipo']}] {text}")
    scanned_any = _ler_anexos_em(stored, texts, anexos, ocr_fn) or scanned_any
    return stored, "\n".join(texts), scanned_any


def _ler_pdf_direto(
    url: str,
    fetch_file,
    anexos: Optional[list[tuple[str, bytes]]] = None,
    ocr_fn=None,
) -> tuple[list[dict[str, Any]], str, bool]:
    """Fonte sem página HTML própria por lote (ex.: TRT5) — a própria URL do
    lote é o edital em PDF, não uma página com <a href> pra PDFs."""
    label = url.rsplit("/", 1)[-1][:80]
    tipo = edital.classify_doc(label, url)
    stored: list[dict[str, Any]] = []
    texts: list[str] = []
    try:
        data = fetch_file(url)
    except Exception:
        data = b""
    item, text, scanned_any = _ler_um(data, {"tipo": tipo, "label": label, "url": url}, ocr_fn)
    stored.append(item)
    if text:
        texts.append(f"[{tipo}] {text}")
    scanned_any = _ler_anexos_em(stored, texts, anexos, ocr_fn) or scanned_any
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
    fetch_infosimples=None,
    fetch_gliner=None,
    fetch_parecer=None,
    fetch_apify=None,
    write_ai: bool = True,
    anexos: Optional[list[tuple[str, bytes]]] = None,
    ocr=None,
) -> dict[str, Any]:
    fetch_page = fetch_page or edital.fetch_html
    fetch_file = fetch_file or edital.fetch_pdf
    ocr_fn = ocr if ocr is not None else ocr_pdf

    # Algumas fontes (TRT5) não têm página HTML própria por lote — a URL do
    # lote já É o edital em PDF. Tratar isso como página quebraria tudo:
    # nunca lia o edital de verdade, "docs" ficava sempre vazio.
    trecho_lote = extra.get("trecho_lote") if isinstance(extra.get("trecho_lote"), str) else ""
    trecho_lote = trecho_lote.strip()
    if url.split("?", 1)[0].lower().endswith(".pdf") and trecho_lote:
        # Edital unificado: ler só o bloco deste imóvel. O PDF inteiro mistura outros bens.
        html, page_text = "", ""
        status = leilao_status(title, description, trecho_lote[:4000])
        page_precos: dict[str, Any] = {}
        page_pracas: list[dict[str, Any]] = []
        html_facts: dict[str, Any] = {}
        stored_docs = [{
            "tipo": "edital",
            "label": "Trecho deste lote no edital unificado",
            "chars": len(trecho_lote),
        }]
        blob, scanned_any = trecho_lote, False
    elif url.split("?", 1)[0].lower().endswith(".pdf"):
        html, page_text = "", ""
        status = leilao_status(title, description, "")
        page_precos = {}
        page_pracas = []
        html_facts = {}
        stored_docs, blob, scanned_any = _ler_pdf_direto(url, fetch_file, anexos=anexos, ocr_fn=ocr_fn)
    else:
        html = fetch_page(url)
        page_text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
        status = leilao_status(title, description, page_text[:4000])
        # 1. Página — preços da praça ativa + rótulos (processo, área, ocupação)
        page_precos = edital.precos_from_page(page_text, html=html)
        page_pracas = pracas_from_html(html)
        html_facts = fatos_from_html(html)
        # 2. PDFs públicos + anexos do usuário — fatos, não preço
        stored_docs, blob, scanned_any = _ler_pdfs(html, url, fetch_file, anexos=anexos, ocr_fn=ocr_fn)

    extracted = edital.fields_from_text(
        blob,
        page_text[:8000],
        source=str(extra.get("source") or ""),
    )
    mix_gliner = "\n".join(p for p in (page_text[:4000], blob[:8000]) if p)
    if extracted.get("ocupacao") == "ocupado":
        extracted["ocupacao"] = ocupacao_se_afirmada(mix_gliner, "ocupado")
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
    for key in ("cidade", "endereco", "matricula", "area", "comitente", "comarca", "descricao"):
        if html_facts.get(key) and not out.get(key):
            out[key] = html_facts[key]
    if html_facts.get("ocupacao"):
        out["ocupacao"] = html_facts["ocupacao"]
    elif extracted.get("ocupacao"):
        out["ocupacao"] = extracted["ocupacao"]
    dividas = dict(extracted.get("dividas") or {})
    html_div = html_facts.get("dividas") if isinstance(html_facts.get("dividas"), dict) else {}
    for key, val in html_div.items():
        dividas.setdefault(key, val)
    if dividas:
        out["dividas"] = dividas
    if stored_docs and not blob.strip():
        out["edital_sem_texto"] = True
    if snap["lance_pagina"]:
        out["lance_pagina"] = snap["lance_pagina"]
    if snap["avaliacao_pagina"]:
        out["avaliacao_pagina"] = snap["avaliacao_pagina"]
        out["avaliacao_edital"] = snap["avaliacao_pagina"]
        if not out.get("avaliacao_fonte"):
            out["avaliacao_fonte"] = "laudo"
    merged_pracas = merge_pracas(out.get("pracas"), page_pracas)
    if merged_pracas:
        out["pracas"] = merged_pracas

    # 3. DataJud — citação só com evidência
    riscos = dict(extracted.get("riscos") or {})
    if html_facts.get("processo_cnj") and not riscos.get("processo_cnj"):
        riscos["processo_cnj"] = html_facts["processo_cnj"]
    gli = fatos_gliner(mix_gliner, fetch=fetch_gliner)
    mesclar_gliner(out, riscos, gli)
    cnj = riscos.get("processo_cnj") or out.get("processo_cnj")
    if isinstance(cnj, str) and cnj:
        dj = consultar_datajud(cnj, fetch=fetch_datajud)
        riscos = merge_riscos(riscos, dj)
    docs_limitados = not _tem_peca_util(stored_docs)
    if docs_limitados:
        from app.ledger import motivo_sem_peca

        motivo = motivo_sem_peca(stored_docs, str(extra.get("source") or ""))
        out["docs_limitados"] = True
        out["sem_norte_motivo"] = motivo
        riscos["docs_limitados"] = True
        riscos["sem_norte_motivo"] = motivo
    curtos = [
        d for d in stored_docs
        if isinstance(d, dict) and d.get("ocr_curto") and isinstance(d.get("trecho"), str) and d["trecho"].strip()
    ]
    if curtos:
        riscos["ocr_curto"] = True
        riscos["ocr_curto_trecho"] = curtos[0]["trecho"].strip()[:220]
    # Infosimples custa R$ 0,20. Uma chamada por avaliação, e só quando há peça
    # útil. Sem peça, o veredito já é Sem norte — não gasta consulta.
    ja_consultado = extra.get("infosimples_consultado_para") == cnj
    if (
        isinstance(cnj, str)
        and cnj
        and not docs_limitados
        and infosimples_disponivel()
        and not ja_consultado
    ):
        info = consultar_infosimples(cnj, fetch=fetch_infosimples)
        out = merge_infosimples(out, info)
    if riscos:
        out["riscos"] = riscos
        if riscos.get("processo_cnj"):
            out["processo_cnj"] = riscos["processo_cnj"]
        if riscos.get("nao_entrar"):
            out["nao_entrar"] = True
        else:
            out.pop("nao_entrar", None)

    out["trechos"] = coletar_trechos(
        page_text=page_text,
        blob=blob,
        riscos=riscos,
        valor_causa=out.get("infosimples_valor_causa")
        if isinstance(out.get("infosimples_valor_causa"), (int, float))
        else None,
        peticoes=out.get("infosimples_peticoes_recentes")
        if isinstance(out.get("infosimples_peticoes_recentes"), list)
        else None,
        stored_docs=stored_docs,
    )

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

    area_mkt = (
        out.get("area_edificacao")
        if isinstance(out.get("area_edificacao"), (int, float))
        else out.get("area")
    )
    mercado = estimate_market_value(
        out.get("cidade") if isinstance(out.get("cidade"), str) else None,
        area_mkt if isinstance(area_mkt, (str, int, float)) else None,
        tipo=tipo,
    )
    if mercado:
        out.update(mercado)
        if out.get("valor_m2_fonte") == "fipezap":
            out.pop("valor_m2_n", None)
    cidade_mkt = out.get("cidade") if isinstance(out.get("cidade"), str) else None
    if cidade_mkt and not isinstance(out.get("valor_mercado_estimado"), (int, float)):
        area_apify = (
            out.get("area_terreno")
            if tipo == "terreno" and isinstance(out.get("area_terreno"), (int, float))
            else area_mkt
        )
        chave = chave_consulta(cidade_mkt, tipo)
        if extra.get("apify_consultado_para") == chave:
            pass
        elif fetch_apify is not None or apify_disponivel():
            info = consultar_apify(
                cidade=cidade_mkt,
                tipo=tipo,
                area=area_apify if isinstance(area_apify, (str, int, float)) else None,
                cnj=out.get("processo_cnj") if isinstance(out.get("processo_cnj"), str) else None,
                fetch=fetch_apify,
            )
            if info:
                out.update(info)
        else:
            out["apify"] = "sem_token"
    area_fecha = _area_m2(
        out.get("area_edificacao")
        if isinstance(out.get("area_edificacao"), (int, float))
        else out.get("area")
    )
    if (
        not isinstance(out.get("valor_mercado_estimado"), (int, float))
        and isinstance(out.get("valor_m2_regiao"), (int, float))
        and area_fecha
    ):
        out["valor_mercado_estimado"] = round(float(out["valor_m2_regiao"]) * area_fecha, 2)

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
        origem=out.get("origem") if isinstance(out.get("origem"), str) else extra.get("origem") if isinstance(extra.get("origem"), str) else None,
        source=str(extra.get("source") or out.get("source") or "") or None,
        pracas=out.get("pracas") if isinstance(out.get("pracas"), list) else None,
        trechos=out.get("trechos") if isinstance(out.get("trechos"), list) else None,
        peticoes=out.get("infosimples_peticoes_recentes")
        if isinstance(out.get("infosimples_peticoes_recentes"), list)
        else None,
        valor_m2_fonte=out.get("valor_m2_fonte") if isinstance(out.get("valor_m2_fonte"), str) else None,
        avaliado=True,
    )
    apply_score(out, score_info)
    if out.get("veredito") == "nao_aprofundar":
        out["nao_entrar"] = True

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
        "infosimples_valor_causa": out.get("infosimples_valor_causa"),
        "infosimples_peticoes_recentes": out.get("infosimples_peticoes_recentes"),
        "trechos": out.get("trechos") or [],
        "texto_docs": "\n".join(p for p in (page_text[:4000], blob[:8000]) if p)[:8000],
        "pracas": out.get("pracas") or [],
        "ledger": out.get("ledger") or [],
        "veredito": out.get("veredito"),
        "veredito_titulo": out.get("veredito_titulo"),
        "veredito_corpo": out.get("veredito_corpo"),
        "regime": out.get("regime"),
    }

    # 5. Parecer — IA lê trechos; OCR conta; PDF escaneado residual não desliga
    usar_ia = write_ai and edital.texto_util_para_parecer(
        blob=blob,
        page_text=page_text,
        trechos=out.get("trechos"),
    )
    parecer = edital._mistral_parecer(facts, fetch=fetch_parecer) if usar_ia else None
    if parecer and edital.parecer_parece_json(parecer):
        parecer = None
    if parecer and status != "encerrado" and re.search(r"\barrematad", parecer, re.I):
        parecer = None
    if parecer and not out.get("nao_entrar") and re.search(r"n[aã]o entre", parecer, re.I):
        parecer = None
    out["parecer"] = parecer or edital.parecer_from_facts(facts)
    return {k: v for k, v in out.items() if v not in (None, "", [], {})}
