"""
Avaliação sob demanda de um lote: PDFs públicos da página do bem,
campos (avaliação, ocupação, dívida), recálculo do score e parecer.

Não roda no scrape. CI cobre parser/parecer com fixture — não baixa PDF ao vivo.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timezone
from io import BytesIO
from typing import Any, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from app.scrapers.extract import extra_json, leilao_status, parse_br_currency
from app.scrapers.listing import HEADERS, href_of, text_of
from app.juridico import riscos_from_text
from app.datajud import consultar_datajud, merge_riscos
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
RE_MONEY = re.compile(r"R\$\s*([\d.]+,\d{2})")
RE_IPTU = re.compile(r"iptu.{0,60}?R\$\s*([\d.]+,\d{2})", re.I)
RE_CONDO = re.compile(
    r"(?:d[eé]bitos?\s+condomin|condom[ií]nio|taxa\s+condomin|despesas?\s+(?:de\s+)?condom)"
    r".{0,80}?R\$\s*([\d.]+,\d{2})",
    re.I,
)
RE_SEM_CONDO = re.compile(
    r"sem\s+(?:d[eé]bitos?|d[ií]vidas?).{0,25}condom|condom[ií]nio.{0,25}sem\s+(?:d[eé]bitos?|d[ií]vidas?)",
    re.I,
)
RE_MENCAO_CONDO = re.compile(
    r"condom[ií]nio.{0,40}(?:atraso|d[eé]bito|inadimpl|dívida)|"
    r"(?:d[eé]bito|dívida|atraso).{0,30}condom",
    re.I,
)
RE_VENAL_IMOVEL = re.compile(
    r"valor\s+venal\s+do\s+im[oó]vel[:\s]*R\$\s*([\d.]+,\d{2})",
    re.I,
)
RE_VENAL_TERRENO = re.compile(
    r"valor\s+venal\s+do\s+terreno[:\s]*R\$\s*([\d.]+,\d{2})",
    re.I,
)
RE_VENAL_EDIF = re.compile(
    r"valor\s+venal\s+(?:da\s+)?edifica[cç][aã]o(?:\s+principal)?[:\s]*R\$\s*([\d.]+,\d{2})",
    re.I,
)
RE_LAUDO = re.compile(
    r"(?:laudo\s+de\s+avalia[cç][aã]o|avalia[cç][aã]o(?:\s+(?:judicial|pericial|atualizada))?|"
    r"valor\s+de\s+mercado)[:\s,]*(?:no\s+valor\s+de\s+)?R\$\s*([\d.]+,\d{2})",
    re.I,
)
RE_AREA_TERRENO = re.compile(r"[aá]rea\s+do\s+terreno[:\s]+([\d.]+,\d+)\s*m", re.I)
RE_AREA_EDIF = re.compile(
    r"(?:edifica[cç][aã]o\s+principal|[aá]rea\s+(?:privativa|constru[ií]da|[úu]til))[:\s]+([\d.]+,\d+)\s*m",
    re.I,
)
MESES = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "março": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}
RE_DATA_NUM = re.compile(r"\b(\d{1,2})[/\.-](\d{1,2})[/\.-]((?:19|20)\d{2})\b")
RE_DATA_EXT = re.compile(
    r"\b(\d{1,2})\s+de\s+(janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\s+de\s+((?:19|20)\d{2})\b",
    re.I,
)
RE_ANO_CTX = re.compile(r"\b((?:19|20)\d{2})\b")
RE_CTX_LAUDO = re.compile(
    r"data[- ]base|data\s+da\s+avalia|laudo|avalia[cç][aã]o",
    re.I,
)
RE_CTX_PROCESSO = re.compile(r"distribu[ií]d|ajuizad|processo\s+n", re.I)
RE_CTX_LIXO = re.compile(
    r"edital|publicad|leil[aã]o|pra[cç]a|venciment|intim|condom|iptu|"
    r"d[ií]vida\s+ativa|refer[eê]ncia|atualiza[cç][aã]o\s+monet|at[eé]\s+\d",
    re.I,
)
RE_VALOR_ATUAL = re.compile(r"valor\s+atual[:\s]*R\$\s*([\d.]+,\d{2})", re.I)
RE_VALOR_AVAL_PAGINA = re.compile(
    r"valor\s+de\s+avalia[cç][aã]o[:\s]*R\$\s*([\d.]+,\d{2})",
    re.I,
)

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


def precos_from_page(page_text: str = "", html: str = "") -> dict[str, float]:
    """Lance e avaliação da página pública. A página manda; o PDF curto não apaga isso."""
    html = (html or "").replace("\xa0", " ").replace("&nbsp;", " ")
    text = (page_text or "").replace("\xa0", " ")
    if html and not text:
        text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    out: dict[str, float] = {}
    if html:
        soup = BeautifulSoup(html, "html.parser")
        for block in soup.select(".product-detail"):
            blob = re.sub(r"\s+", " ", block.get_text(" ", strip=True))
            money = parse_br_currency(m.group(1)) if (m := re.search(r"R\$\s*([\d.]+,\d{2})", blob)) else None
            if not money or money <= 0:
                continue
            low = blob.lower()
            if low.startswith("valor atual"):
                out["lance_pagina"] = money
            elif low.startswith("valor de avalia"):
                out["avaliacao_pagina"] = money
    if "lance_pagina" not in out:
        atual = parse_br_currency(m.group(1)) if (m := RE_VALOR_ATUAL.search(text)) else None
        if atual and atual > 0:
            out["lance_pagina"] = atual
    if "avaliacao_pagina" not in out:
        aval = parse_br_currency(m.group(1)) if (m := RE_VALOR_AVAL_PAGINA.search(text)) else None
        if aval and aval > 0:
            out["avaliacao_pagina"] = aval
    return out


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


def _money(pattern: re.Pattern[str], blob: str) -> Optional[float]:
    found = pattern.search(blob)
    if not found:
        return None
    value = parse_br_currency(found.group(1))
    return value if value and value > 0 else None


def _area(pattern: re.Pattern[str], blob: str) -> Optional[float]:
    found = pattern.search(blob)
    if not found:
        return None
    value = parse_br_currency(found.group(1))
    return value if value and value > 0 else None


def _safe_date(year: int, month: int, day: int) -> Optional[date]:
    try:
        value = date(year, month, day)
    except ValueError:
        return None
    if value.year < 1980 or value > date.today():
        return None
    return value


def _last_end(pattern: re.Pattern[str], text: str) -> int:
    matches = list(pattern.finditer(text))
    return matches[-1].end() if matches else -1


def _context_kind(snippet: str) -> Optional[str]:
    """O rótulo mais perto da data ganha. 'Edital... Data da avaliação: 2015' conta como laudo."""
    laudo_at = _last_end(RE_CTX_LAUDO, snippet)
    proc_at = _last_end(RE_CTX_PROCESSO, snippet)
    lixo_at = _last_end(RE_CTX_LIXO, snippet)
    best = max(laudo_at, proc_at)
    if best < 0:
        return None
    if lixo_at > best:
        return None
    return "laudo" if laudo_at >= proc_at else "processo"


def avaliacao_data_from_text(blob: str) -> dict[str, str]:
    """Data do laudo (preferida) ou da distribuição do processo. Ignora edital/IPTU."""
    found: list[tuple[date, str]] = []
    for match in RE_DATA_NUM.finditer(blob):
        day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        quando = _safe_date(year, month, day)
        if not quando:
            continue
        start = max(0, match.start() - 90)
        kind = _context_kind(blob[start:match.start()])
        if kind:
            found.append((quando, kind))
    for match in RE_DATA_EXT.finditer(blob):
        day = int(match.group(1))
        month = MESES.get(match.group(2).lower().replace("ç", "c"), 0)
        year = int(match.group(3))
        quando = _safe_date(year, month, day) if month else None
        if not quando:
            continue
        start = max(0, match.start() - 90)
        kind = _context_kind(blob[start:match.start()])
        if kind:
            found.append((quando, kind))
    if not found:
        for match in RE_ANO_CTX.finditer(blob):
            year = int(match.group(1))
            quando = _safe_date(year, 6, 30)
            if not quando:
                continue
            start = max(0, match.start() - 50)
            kind = _context_kind(blob[start:match.start()])
            if kind:
                found.append((quando, kind))
    if not found:
        return {}
    laudos = [item for item in found if item[1] == "laudo"]
    escolhidos = laudos or [item for item in found if item[1] == "processo"]
    if not escolhidos:
        return {}
    quando, origem = min(escolhidos, key=lambda item: item[0])
    return {"avaliacao_data": quando.isoformat(), "avaliacao_data_origem": origem}


def _pick_avaliacao(blob: str) -> dict[str, Any]:
    """Laudo/avaliação judicial ganha. Venal do imóvel ≠ venal do terreno."""
    out: dict[str, Any] = {}
    venal_imovel = _money(RE_VENAL_IMOVEL, blob)
    venal_terreno = _money(RE_VENAL_TERRENO, blob)
    venal_edif = _money(RE_VENAL_EDIF, blob)
    if venal_terreno:
        out["valor_venal_terreno"] = venal_terreno
    if venal_edif:
        out["valor_venal_edificacao"] = venal_edif
    if venal_imovel:
        out["valor_venal_imovel"] = venal_imovel
    elif venal_terreno and venal_edif:
        out["valor_venal_imovel"] = round(venal_terreno + venal_edif, 2)

    laudo = _money(RE_LAUDO, blob)
    # "valor venal do terreno" não pode vazar como laudo: o padrão de laudo
    # não inclui a palavra venal, mas um "avaliação ... R$" genérico sim.
    if laudo and venal_terreno and abs(laudo - venal_terreno) < 0.01:
        laudo = None
    if laudo and out.get("valor_venal_imovel") and abs(laudo - out["valor_venal_imovel"]) < 0.01:
        laudo = None
    if laudo and venal_edif and abs(laudo - venal_edif) < 0.01:
        laudo = None
    if laudo and laudo > 1000:
        out["avaliacao_edital"] = laudo
        out["avaliacao_fonte"] = "laudo"
    elif out.get("valor_venal_imovel") and out["valor_venal_imovel"] > 1000:
        out["avaliacao_edital"] = out["valor_venal_imovel"]
        out["avaliacao_fonte"] = "venal_imovel"
    elif venal_edif and venal_edif > 1000:
        out["avaliacao_edital"] = venal_edif
        out["avaliacao_fonte"] = "venal_imovel"
    elif venal_terreno and venal_terreno > 1000 and not venal_edif:
        out["avaliacao_edital"] = venal_terreno
        out["avaliacao_fonte"] = "venal_imovel"
    return out


def fields_from_text(blob: str, page_text: str = "", source: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    out.update(_pick_avaliacao(blob))
    out.update(avaliacao_data_from_text(blob))
    area_terreno = _area(RE_AREA_TERRENO, blob)
    area_edif = _area(RE_AREA_EDIF, blob)
    if area_terreno:
        out["area_terreno"] = area_terreno
    if area_edif:
        out["area_edificacao"] = area_edif
        out["area"] = f"{area_edif:.2f} m²".replace(".", ",")
    desocupado = bool(RE_DESOCUPADO.search(blob))
    ocupado = bool(RE_OCUPADO.search(blob)) and not desocupado
    if desocupado:
        out["ocupacao"] = "desocupado"
    elif ocupado:
        out["ocupacao"] = "ocupado"
    iptu = parse_br_currency(m.group(1)) if (m := RE_IPTU.search(blob)) else None
    condo_vals = [parse_br_currency(m.group(1)) for m in RE_CONDO.finditer(blob)]
    condo_vals = [v for v in condo_vals if v and v > 0]
    condo = max(condo_vals) if condo_vals else None
    sem_condo = bool(RE_SEM_CONDO.search(blob))
    sem_divida = bool(re.search(r"sem\s+(?:d[eé]bitos?|d[ií]vidas?)", blob, re.I))
    mencao_condo = bool(RE_MENCAO_CONDO.search(blob)) and not sem_condo
    if sem_condo:
        condo = None
        mencao_condo = False
    if iptu or condo or mencao_condo:
        dividas: dict[str, Any] = {}
        if iptu:
            dividas["iptu"] = iptu
        if condo:
            dividas["condominio"] = condo
        if mencao_condo:
            dividas["mencao_condominio"] = True
        out["dividas"] = dividas
        out["tem_divida"] = bool(condo or mencao_condo)
    elif desocupado or ocupado or sem_divida:
        out["tem_divida"] = False
    riscos = riscos_from_text(blob, page_text, source=source)
    if riscos:
        out["riscos"] = riscos
        if riscos.get("processo_cnj"):
            out["processo_cnj"] = riscos["processo_cnj"]
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
    status = facts.get("status")
    if status == "aguardando":
        linhas.insert(0, "Leilão ainda não abriu para lances.")
    elif status == "encerrado":
        linhas.insert(0, "Lote encerrado ou já arrematado — fora do catálogo de trabalho.")
    lance = facts.get("lance_atual")
    if isinstance(lance, (int, float)) and status != "encerrado":
        linhas.append(f"Lance pedido agora: R$ {lance:,.2f}.".replace(",", "X").replace(".", ",").replace("X", "."))
    fonte = facts.get("avaliacao_fonte")
    aval = facts.get("avaliacao_edital")
    venal_t = facts.get("valor_venal_terreno")
    if fonte == "venal_imovel" and isinstance(aval, (int, float)):
        linhas.append(
            f"Valor venal do imóvel (IPTU): R$ {aval:,.2f}.".replace(",", "X").replace(".", ",").replace("X", ".")
        )
        if isinstance(venal_t, (int, float)):
            linhas.append(
                f"Não usar o venal do terreno (R$ {venal_t:,.2f}) como valor do imóvel.".replace(",", "X").replace(".", ",").replace("X", ".")
            )
    area_e = facts.get("area_edificacao")
    if isinstance(area_e, (int, float)):
        linhas.append(f"Área da edificação: {area_e:.2f} m².".replace(".", ","))
    data_aval = facts.get("avaliacao_data")
    if isinstance(data_aval, str) and data_aval:
        origem = "processo" if facts.get("avaliacao_data_origem") == "processo" else "laudo"
        linhas.append(f"Data do {origem}: {data_aval}.")
    if facts.get("scanned"):
        linhas.append("Há PDF escaneado sem texto extraível; OCR fica para um próximo passo.")
    riscos = facts.get("riscos") if isinstance(facts.get("riscos"), dict) else {}
    if facts.get("docs_limitados") or riscos.get("docs_limitados"):
        linhas.append(
            "Matrícula e laudo sem texto extraível; a leitura ficou no edital/página. "
            "Não dá para afirmar meação, citação nem ocupação."
        )
    if riscos.get("datajud") in ("nao_encontrado", "indisponivel"):
        linhas.append("DataJud não trouxe movimentos deste processo; citação não confirmada.")
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
        "avaliacao_fonte": facts.get("avaliacao_fonte"),
        "valor_venal_imovel": facts.get("valor_venal_imovel"),
        "valor_venal_terreno": facts.get("valor_venal_terreno"),
        "area_edificacao": facts.get("area_edificacao"),
        "area_terreno": facts.get("area_terreno"),
        "avaliacao_data": facts.get("avaliacao_data"),
        "avaliacao_data_origem": facts.get("avaliacao_data_origem"),
        "lance_atual": facts.get("lance_atual"),
        "status": facts.get("status") or "aberto",
        "ocupacao": facts.get("ocupacao"),
        "dividas": facts.get("dividas"),
        "docs": [d.get("label") for d in (facts.get("docs") or []) if isinstance(d, dict)],
        "scanned": bool(facts.get("scanned")),
        "cidade": facts.get("cidade"),
        "headline": facts.get("headline"),
        "processo_cnj": facts.get("processo_cnj"),
        "riscos": facts.get("riscos"),
        "docs_limitados": bool(facts.get("docs_limitados")),
        "nao_entrar": bool((facts.get("riscos") or {}).get("nao_entrar") or facts.get("nao_entrar")),
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
                            "lance_atual é o preço pedido agora, NÃO valor de arrematação. "
                            "Nunca escreva que o imóvel foi arrematado, vendido ou encerrado "
                            "salvo se status for encerrado. "
                            "Se status for aguardando, diga que o leilão ainda não abriu. "
                            "Valor venal do terreno NÃO é o valor do imóvel; use avaliacao "
                            "ou valor_venal_imovel. Área útil é area_edificacao, não area_terreno. "
                            "avaliacao_fonte=venal_imovel é IPTU, não laudo de mercado. "
                            "avaliacao_data antiga é oportunidade: o juiz costuma só corrigir "
                            "monetariamente, abaixo do mercado. 1 ano já é bom; 5+ melhor; 10+ melhor ainda. "
                            "Lance acima de laudo antigo NÃO é overpay e NÃO é ponto negativo. "
                            "IPTU em leilão judicial em geral é abatido; condomínio NÃO se abate. "
                            "Lance atual acima do inicial é concorrência, não ponto negativo. "
                            "Alerta o lance atual em relação à avaliação recente; laudo antigo continua oportunidade. "
                            "Leiloeiro da mesma casa (Calil, Zuk, Vegas, Mega, Lance) no site e no edital "
                            "é o mesmo — não diga divergência. "
                            "citacao nao_citado ou pendente: diga para não entrar. "
                            "Usufruto só se riscos.usufruto. Meação só se riscos.meacao for true — "
                            "fração ideal de condomínio e regra genérica de cônjuge NÃO são meação. "
                            "Não diga 'não entre' salvo se nao_entrar for true. "
                            "Não invente praça, desconto judicial, ocupação nem débito. "
                            "avaliacao_data_origem=processo é a data do processo, NÃO do laudo. "
                            "Se datajud for nao_encontrado ou indisponivel, diga que o DataJud "
                            "não trouxe movimentos. Se docs_limitados, diga que faltou texto de "
                            "matrícula/laudo e não afirme o que não leu. "
                            "DataJud só traz movimentos, não peças do processo. "
                            "Não use adjetivo de venda. Se faltar dado, diga que falta. "
                            "Explique o score com os motivos."
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
    fetch_datajud=None,
    write_ai: bool = True,
) -> dict[str, Any]:
    """Lê a página do lote, PDFs públicos, devolve extra enriquecido. Não inventa."""
    html = fetch_page(url)
    page_text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    status = leilao_status(title, description, page_text[:4000])
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
    extracted = fields_from_text(
        blob,
        page_text[:8000],
        source=str(extra.get("source") or ""),
    )
    out = dict(extra)
    out["docs"] = stored_docs
    out["avaliado_em"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out["status"] = status
    for key in (
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
    ):
        if extracted.get(key) not in (None, "", [], {}):
            out[key] = extracted[key]
    if extracted.get("ocupacao"):
        out["ocupacao"] = extracted["ocupacao"]
    if extracted.get("dividas"):
        out["dividas"] = extracted["dividas"]
    if stored_docs and not blob.strip():
        out["edital_sem_texto"] = True

    page_precos = precos_from_page(page_text, html=html)
    if page_precos.get("lance_pagina"):
        out["lance_pagina"] = page_precos["lance_pagina"]
    if page_precos.get("avaliacao_pagina"):
        out["avaliacao_pagina"] = page_precos["avaliacao_pagina"]
        out["avaliacao_edital"] = page_precos["avaliacao_pagina"]
        if not out.get("avaliacao_fonte"):
            out["avaliacao_fonte"] = "laudo"
    lance_score = page_precos.get("lance_pagina") or current_bid

    riscos = dict(extracted.get("riscos") or {})
    cnj = riscos.get("processo_cnj")
    if isinstance(cnj, str) and cnj:
        dj = consultar_datajud(cnj, fetch=fetch_datajud)
        riscos = merge_riscos(riscos, dj)
    tem_peca = any(
        isinstance(d, dict)
        and d.get("tipo") in ("laudo", "matricula", "penhora")
        and int(d.get("chars") or 0) >= 80
        and not d.get("scanned")
        for d in stored_docs
    )
    if not tem_peca:
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

    ref = out.get("avaliacao_edital") or page_precos.get("avaliacao_pagina") or reference_value
    tem_divida = extracted.get("tem_divida")
    ocupacao = out.get("ocupacao") if isinstance(out.get("ocupacao"), str) else None
    fonte = out.get("avaliacao_fonte") if out.get("avaliacao_fonte") in ("laudo", "venal_imovel") else None
    desc = " ".join(p for p in (description, blob[:3000]) if p)
    score_info = compute_score(
        title=title,
        description=desc,
        current_bid=lance_score,
        minimum_bid=minimum_bid,
        reference_value=ref if isinstance(ref, (int, float)) else None,
        valor_mercado_estimado=out.get("valor_mercado_estimado")
        if isinstance(out.get("valor_mercado_estimado"), (int, float))
        else None,
        ocupacao=ocupacao,
        tem_divida=tem_divida if isinstance(tem_divida, bool) else None,
        fonte_avaliacao=fonte,
        dividas=out.get("dividas") if isinstance(out.get("dividas"), dict) else None,
        avaliacao_data=out.get("avaliacao_data"),
        avaliacao_data_origem=out.get("avaliacao_data_origem")
        if out.get("avaliacao_data_origem") in ("laudo", "processo")
        else None,
        tipo=out.get("tipo") if isinstance(out.get("tipo"), str) else None,
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
        "lance_atual": lance_score if lance_score is not None else minimum_bid,
        "status": status,
        "ocupacao": ocupacao,
        "dividas": out.get("dividas"),
        "docs": stored_docs,
        "scanned": scanned_any,
        "docs_limitados": bool(out.get("docs_limitados")),
        "cidade": out.get("cidade"),
        "headline": out.get("headline"),
        "processo_cnj": out.get("processo_cnj"),
        "riscos": riscos or None,
        "nao_entrar": bool(out.get("nao_entrar")),
    }
    analise_limitada = bool(out.get("docs_limitados") or out.get("edital_sem_texto") or scanned_any)
    parecer = _mistral_parecer(facts) if write_ai and not analise_limitada else None
    if parecer and status != "encerrado" and re.search(r"\barrematad", parecer, re.I):
        parecer = None
    if parecer and not out.get("nao_entrar") and re.search(r"n[aã]o entre", parecer, re.I):
        parecer = None
    out["parecer"] = parecer or parecer_from_facts(facts)
    return {k: v for k, v in out.items() if v not in (None, "", [], {})}


def apply_avaliacao_to_lot(lot, extra: dict[str, Any]) -> None:
    aval = extra.get("avaliacao_edital")
    if isinstance(aval, (int, float)) and aval > 0:
        lot.reference_value = float(aval)
    lance = extra.get("lance_pagina")
    if isinstance(lance, (int, float)) and lance > 0:
        lot.current_bid = float(lance)
        lot.minimum_bid = float(lance)
    aval_pagina = extra.get("avaliacao_pagina")
    if isinstance(aval_pagina, (int, float)) and aval_pagina > 0:
        lot.reference_value = float(aval_pagina)
    lot.raw_data = extra_json(extra)
    lot.updated_at = datetime.utcnow()
