"""
Avaliação sob demanda de um lote: PDFs públicos da página do bem,
campos (avaliação, ocupação, dívida), recálculo do score e parecer.

Não roda no scrape. CI cobre parser/parecer com fixture — não baixa PDF ao vivo.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from app.scrapers.extract import extra_json, parse_br_currency
from app.scrapers.listing import HEADERS, href_of, text_of
from app.scoring import RE_DESOCUPADO, RE_DIVIDA, RE_OCUPADO, compute_score

MAX_PDFS = 4
MAX_PDF_BYTES = 8_000_000
MAX_PAGES = 12
MAX_TEXT = 14_000
PDF_TIMEOUT = 30.0

SKIP_HREF = re.compile(
    r"proposta|politica|privacidade|cookie|termos-de-uso|modelo-de-proposta",
    re.I,
)
RE_AVALIACAO = re.compile(
    r"(?:avalia[cç][aã]o(?:\s+(?:judicial|pericial|atualizada))?|valor\s+(?:venal|de\s+mercado))"
    r".{0,80}?R\$\s*([\d.]+,\d{2})",
    re.I,
)
RE_MONEY = re.compile(r"R\$\s*([\d.]+,\d{2})")
RE_IPTU = re.compile(r"iptu.{0,60}?R\$\s*([\d.]+,\d{2})", re.I)
RE_CONDO = re.compile(r"condom[ií]nio.{0,60}?R\$\s*([\d.]+,\d{2})", re.I)

DOC_TIPOS: list[tuple[str, re.Pattern[str]]] = [
    ("laudo", re.compile(r"laudo|avalia", re.I)),
    ("edital", re.compile(r"edital", re.I)),
    ("debito", re.compile(r"d[eé]bito|condomin", re.I)),
    ("iptu", re.compile(r"iptu|municip", re.I)),
    ("matricula", re.compile(r"matr[ií]cula", re.I)),
    ("penhora", re.compile(r"penhora", re.I)),
]


def abs_pdf_url(base: str, href: str) -> str:
    if not href:
        return ""
    if href.startswith("//"):
        return "https:" + href
    return urljoin(base, href)


def classify_doc(label: str, url: str) -> str:
    blob = f"{label} {url}"
    for name, pattern in DOC_TIPOS:
        if pattern.search(blob):
            return name
    return "documento"


def collect_pdfs(html: str, base_url: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for a in soup.select("a[href]"):
        href = href_of(a)
        if ".pdf" not in href.lower():
            continue
        if SKIP_HREF.search(href):
            continue
        url = abs_pdf_url(base_url, href)
        if not url.startswith("http") or url in seen:
            continue
        seen.add(url)
        label = text_of(a) or url.rsplit("/", 1)[-1]
        label = re.sub(r"\s+", " ", label).strip()[:80]
        tipo = classify_doc(label, url)
        out.append({"tipo": tipo, "label": label or tipo, "url": url})
    rank = {"laudo": 0, "edital": 1, "debito": 2, "iptu": 3, "matricula": 4, "penhora": 5, "documento": 6}
    out.sort(key=lambda d: rank.get(d["tipo"], 9))
    return out[:MAX_PDFS]


def extract_pdf_text(data: bytes) -> tuple[str, bool]:
    if not data or not data.startswith(b"%PDF") or len(data) < 64:
        return "", True
    try:
        reader = PdfReader(BytesIO(data))
        parts: list[str] = []
        for page in reader.pages[:MAX_PAGES]:
            parts.append(page.extract_text() or "")
        text = re.sub(r"[ \t]+", " ", "\n".join(parts))
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
    except Exception:
        return "", True
    scanned = len(text) < 80
    return text[:MAX_TEXT], scanned


def fields_from_text(blob: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    found = RE_AVALIACAO.search(blob)
    if found:
        value = parse_br_currency(found.group(1))
        if value and value > 1000:
            out["avaliacao_edital"] = value
    desocupado = bool(RE_DESOCUPADO.search(blob))
    ocupado = bool(RE_OCUPADO.search(blob)) and not desocupado
    if desocupado:
        out["ocupacao"] = "desocupado"
    elif ocupado:
        out["ocupacao"] = "ocupado"
    iptu = parse_br_currency(m.group(1)) if (m := RE_IPTU.search(blob)) else None
    condo = parse_br_currency(m.group(1)) if (m := RE_CONDO.search(blob)) else None
    sem_divida = bool(re.search(r"sem\s+(?:d[eé]bitos?|d[ií]vidas?)", blob, re.I))
    tem_divida = (bool(RE_DIVIDA.search(blob)) or bool(iptu) or bool(condo)) and not sem_divida
    if tem_divida or iptu or condo:
        dividas: dict[str, Any] = {}
        if iptu:
            dividas["iptu"] = iptu
        if condo:
            dividas["condominio"] = condo
        if tem_divida:
            dividas["mencao"] = True
        out["dividas"] = dividas
        out["tem_divida"] = True
    elif desocupado or ocupado:
        out["tem_divida"] = False
    return out


def parecer_from_facts(facts: dict[str, Any]) -> str:
    """Parecer objetivo sem inventar número. Usado no CI e se a IA falhar."""
    score = facts.get("score")
    linhas = []
    if isinstance(score, int):
        comparacao = "com preço de referência" if facts.get("tem_comparacao_preco") else "parcial, sem preço de referência"
        linhas.append(f"Score {score}/100 ({comparacao}).")
    for motivo in facts.get("motivos") or []:
        linhas.append(str(motivo).rstrip(".") + ".")
    docs = facts.get("docs") or []
    if docs:
        nomes = ", ".join(d.get("label") or d.get("tipo") for d in docs[:6] if isinstance(d, dict))
        linhas.append(f"Documentos lidos: {nomes}.")
    if facts.get("scanned"):
        linhas.append("Há PDF escaneado sem texto extraível; OCR fica para um próximo passo.")
    if not linhas:
        return "Não foi possível montar o parecer com os indícios disponíveis."
    return " ".join(linhas)


def _mistral_parecer(facts: dict[str, Any]) -> str | None:
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        return None
    model = (
        os.getenv("OPENROUTER_WRITE_MODEL")
        or os.getenv("OPENROUTER_EXTRACT_MODEL")
        or "mistralai/ministral-8b-2512"
    ).strip()
    payload = {
        "score": facts.get("score"),
        "motivos": facts.get("motivos") or [],
        "avaliacao": facts.get("avaliacao_edital"),
        "lance": facts.get("lance"),
        "ocupacao": facts.get("ocupacao"),
        "dividas": facts.get("dividas"),
        "docs": [d.get("label") for d in (facts.get("docs") or []) if isinstance(d, dict)],
        "scanned": bool(facts.get("scanned")),
        "cidade": facts.get("cidade"),
        "headline": facts.get("headline"),
    }
    try:
        r = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL") or "http://127.0.0.1:8050",
                "X-Title": os.getenv("OPENROUTER_APP_NAME") or "leiloes",
            },
            json={
                "model": model,
                "temperature": 0.2,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Você é analista de leilão judicial de imóvel no Brasil. "
                            "Escreva 2 parágrafos curtos, objetivos, em português. "
                            "Use só os fatos do JSON. Não invente valor, dívida, ocupação nem desconto. "
                            "Não use adjetivo de venda (imperdível, oportunidade única). "
                            "Se faltar dado, diga que falta. Explique o score com os motivos."
                        ),
                    },
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
            },
            timeout=40.0,
        )
        if r.status_code >= 400:
            return None
        content = (((r.json().get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
        text = str(content).strip()
        return text[:1800] if text else None
    except Exception:
        return None


def fetch_html(url: str) -> str:
    with httpx.Client(timeout=25.0, follow_redirects=True, headers=HEADERS) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.text


def fetch_pdf(url: str) -> bytes:
    headers = {**HEADERS, "Accept": "application/pdf,*/*"}
    with httpx.Client(timeout=PDF_TIMEOUT, follow_redirects=True, headers=headers) as client:
        r = client.get(url)
        r.raise_for_status()
        data = r.content
        if len(data) > MAX_PDF_BYTES:
            return data[:MAX_PDF_BYTES]
        return data


def avaliar_lote(
    *,
    title: str,
    description: Optional[str],
    url: str,
    current_bid: Optional[float],
    minimum_bid: Optional[float],
    reference_value: Optional[float],
    extra: dict[str, Any],
    fetch_page=fetch_html,
    fetch_file=fetch_pdf,
    write_ai: bool = True,
) -> dict[str, Any]:
    """Lê a página do lote, PDFs públicos, devolve extra enriquecido. Não inventa."""
    html = fetch_page(url)
    docs = collect_pdfs(html, url)
    texts: list[str] = []
    scanned_any = False
    stored_docs: list[dict[str, Any]] = []
    for doc in docs:
        item = dict(doc)
        try:
            data = fetch_file(doc["url"])
            text, scanned = extract_pdf_text(data)
        except Exception:
            text, scanned = "", True
        if scanned:
            scanned_any = True
            item["scanned"] = True
        item["chars"] = len(text)
        stored_docs.append(item)
        if text:
            texts.append(f"[{doc['tipo']}] {text}")

    blob = "\n".join(texts)
    extracted = fields_from_text(blob)
    out = dict(extra)
    out["docs"] = stored_docs
    out["avaliado_em"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if extracted.get("avaliacao_edital"):
        out["avaliacao_edital"] = extracted["avaliacao_edital"]
    if extracted.get("ocupacao"):
        out["ocupacao"] = extracted["ocupacao"]
    if extracted.get("dividas"):
        out["dividas"] = extracted["dividas"]
    if stored_docs and not blob.strip():
        out["edital_sem_texto"] = True

    ref = out.get("avaliacao_edital") or reference_value
    tem_divida = extracted.get("tem_divida")
    ocupacao = out.get("ocupacao") if isinstance(out.get("ocupacao"), str) else None
    desc = " ".join(p for p in (description, blob[:3000]) if p)
    score_info = compute_score(
        title=title,
        description=desc,
        current_bid=current_bid,
        minimum_bid=minimum_bid,
        reference_value=ref if isinstance(ref, (int, float)) else None,
        valor_mercado_estimado=out.get("valor_mercado_estimado")
        if isinstance(out.get("valor_mercado_estimado"), (int, float))
        else None,
        ocupacao=ocupacao,
        tem_divida=tem_divida if isinstance(tem_divida, bool) else None,
    )
    out["score"] = score_info["score"]
    out["score_tem_comparacao_preco"] = score_info["tem_comparacao_preco"]
    out["score_motivos"] = score_info["motivos"]

    facts = {
        "score": out["score"],
        "tem_comparacao_preco": out["score_tem_comparacao_preco"],
        "motivos": out["score_motivos"],
        "avaliacao_edital": out.get("avaliacao_edital"),
        "lance": current_bid if current_bid is not None else minimum_bid,
        "ocupacao": ocupacao,
        "dividas": out.get("dividas"),
        "docs": stored_docs,
        "scanned": scanned_any,
        "cidade": out.get("cidade"),
        "headline": out.get("headline"),
    }
    parecer = _mistral_parecer(facts) if write_ai else None
    out["parecer"] = parecer or parecer_from_facts(facts)
    return {k: v for k, v in out.items() if v not in (None, "", [], {})}


def apply_avaliacao_to_lot(lot, extra: dict[str, Any]) -> None:
    aval = extra.get("avaliacao_edital")
    if isinstance(aval, (int, float)) and aval > 0 and lot.reference_value is None:
        lot.reference_value = float(aval)
    lot.raw_data = extra_json(extra)
    lot.updated_at = datetime.utcnow()
