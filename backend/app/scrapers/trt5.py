"""
TRT5 (Tribunal Regional do Trabalho da 5ª Região, BA) — editais publicados
na lista pública do tribunal. Sem login.

"Edital de Alienação" vira um lote, como antes.
"Leilão Unificado" é um PDF público com vários imóveis: cada bloco "Lote: N"
vira um lote. O texto daquele bloco segue com o lote. Isso não é matrícula.
"""
from __future__ import annotations

import json
import re

import httpx
from bs4 import BeautifulSoup, Tag

from app.edital import extract_pdf_text
from app.scrapers.extract import extra_json

from .base import BaseScraper, ScrapedAuction, ScrapedLot
from .listing import HEADERS, abs_url, cidade_from_text, extra_lot, tipo_from_text

RE_ALIENACAO = re.compile(r"edital\s+de\s+aliena[cç][aã]o", re.I)
RE_UNIFICADO = re.compile(r"leil[aã]o\s+unificado", re.I)
RE_PROCESSO = re.compile(r"(?:PROCESSO|REEF)\s*[:.]?\s*([\d./-]{8,30})", re.I)
RE_LOTE = re.compile(r"Lote:\s*(\d+)\b", re.I)
RE_CNJ = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")
RE_BENS = re.compile(
    r"Bens:\s*(.+?)(?=Localiza[cç][aã]o do Bem:|Avalia[cç][aã]o:|$)",
    re.I | re.S,
)
RE_LOCAL = re.compile(
    r"Localiza[cç][aã]o do Bem:\s*(.+?)(?=Avalia[cç][aã]o:|Data do leil[aã]o:|$)",
    re.I | re.S,
)
RE_AVAL = re.compile(r"Avalia[cç][aã]o:\s*R\$\s*([\d.]+,\d{2})", re.I)
RE_LANCE = re.compile(r"Lance M[ií]nimo:\s*R\$\s*([\d.]+,\d{2})", re.I)
RE_VEICULO_LOTE = re.compile(r"\bcaminh[aã]o\b|\bve[ií]culo\b", re.I)
MAX_UNIFICADO = 6
MAX_PDF_BYTES = 8_000_000


class Trt5Scraper(BaseScraper):
    source_name = "trt5"
    base_url = "https://www.trt5.jus.br"

    async def scrape(self) -> list[ScrapedAuction]:
        by_id: dict[str, ScrapedLot] = {}
        pdfs: list[tuple[str, str]] = []
        seen_pdf: set[str] = set()
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=HEADERS) as client:
            for page in range(0, 10):
                url = f"{self.base_url}/execucoes-leiloes/leiloes"
                if page > 0:
                    url = f"{url}?page={page}"
                try:
                    r = await client.get(url)
                    r.raise_for_status()
                except Exception:
                    break
                found = lots_from_html(r.text, self.base_url)
                new = 0
                for lot in found:
                    if lot.external_id not in by_id:
                        by_id[lot.external_id] = lot
                        new += 1
                added_pdf = 0
                for title, pdf_url in unificado_links(r.text, self.base_url):
                    if len(pdfs) >= MAX_UNIFICADO:
                        break
                    if pdf_url not in seen_pdf:
                        seen_pdf.add(pdf_url)
                        pdfs.append((title, pdf_url))
                        added_pdf += 1
                if (not found or new == 0) and added_pdf == 0:
                    break
            for title, pdf_url in pdfs:
                try:
                    resp = await client.get(pdf_url)
                    resp.raise_for_status()
                except Exception:
                    continue
                text, scanned = extract_pdf_text(resp.content[:MAX_PDF_BYTES])
                if scanned or not text.strip():
                    continue
                for lot in lots_from_unificado(title, pdf_url, text):
                    if lot.external_id not in by_id:
                        by_id[lot.external_id] = lot
        lots = list(by_id.values())
        if not lots:
            return []
        return [
            ScrapedAuction(
                external_id="trt5-alienacoes",
                source=self.source_name,
                title="TRT5 — Editais de Alienação Judicial",
                url=f"{self.base_url}/execucoes-leiloes/leiloes",
                description=f"{len(lots)} lote(s) públicos",
                lots=lots,
            )
        ]


def lots_from_html(html: str, base_url: str) -> list[ScrapedLot]:
    soup = BeautifulSoup(html, "html.parser")
    lots: list[ScrapedLot] = []
    seen: set[str] = set()
    for a in soup.select('a[href*=".pdf"]'):
        title = a.get_text(strip=True)
        if not RE_ALIENACAO.search(title):
            continue
        tipo = tipo_from_text(title)
        if tipo == "veiculo":
            continue
        href = _href(a)
        if not href:
            continue
        url = abs_url(base_url, href)
        proc = RE_PROCESSO.search(title)
        base_id = proc.group(1) if proc else title[:60]
        external_id = f"{base_id}:{href.rsplit('/', 1)[-1]}"[:128]
        if external_id in seen:
            continue
        seen.add(external_id)
        cidade = cidade_from_text(title)
        raw = extra_lot(title=title, cidade=cidade, endereco=None, tipo=tipo, foto=None, origem="trt5")
        lots.append(
            ScrapedLot(
                external_id=external_id,
                title=title[:512],
                description=None,
                category=tipo,
                minimum_bid=None,
                current_bid=None,
                url=url,
                raw_data=raw,
            )
        )
    return lots


def unificado_links(html: str, base_url: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for a in soup.select('a[href*=".pdf"]'):
        title = a.get_text(strip=True)
        if not RE_UNIFICADO.search(title):
            continue
        href = _href(a)
        if not href:
            continue
        url = abs_url(base_url, href)
        if url in seen:
            continue
        seen.add(url)
        found.append((title, url))
    return found


def split_unificado(text: str) -> list[dict]:
    """Cada bloco 'Lote: N' do anexo público vira um imóvel. Sem matrícula à parte."""
    marks = list(RE_LOTE.finditer(text))
    itens: list[dict] = []
    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        chunk = text[mark.start() : end]
        bens_m = RE_BENS.search(chunk)
        bens = _one_line(bens_m.group(1))[:400] if bens_m else ""
        if len(bens) < 8:
            continue
        local_m = RE_LOCAL.search(chunk)
        local = _one_line(local_m.group(1))[:180] if local_m else None
        proc = RE_CNJ.search(chunk)
        aval = RE_AVAL.search(chunk)
        lance = RE_LANCE.search(chunk)
        itens.append(
            {
                "n": int(mark.group(1)),
                "processo": proc.group(0) if proc else None,
                "bens": bens,
                "local": local,
                "avaliacao": _money(aval.group(1)) if aval else None,
                "lance": _money(lance.group(1)) if lance else None,
                "trecho": _one_line(chunk)[:1200],
            }
        )
    return itens


def lots_from_unificado(link_title: str, url: str, text: str) -> list[ScrapedLot]:
    fname = url.rstrip("/").rsplit("/", 1)[-1][:40]
    lots: list[ScrapedLot] = []
    for item in split_unificado(text):
        tipo = tipo_from_text(item["bens"])
        if tipo == "veiculo" or RE_VEICULO_LOTE.search(item["bens"]):
            continue
        cidade = cidade_from_text(item["local"] or "", item["bens"])
        proc = item["processo"] or "sem-processo"
        raw = extra_lot(
            title=item["bens"],
            cidade=cidade,
            endereco=item["local"],
            tipo=tipo,
            foto=None,
            origem="trt5",
        )
        payload = json.loads(raw) if raw else {}
        payload["trecho_lote"] = item["trecho"]
        payload["unificado"] = True
        if item["processo"]:
            payload["processo_cnj"] = item["processo"]
        payload["edital_unificado"] = link_title[:180]
        lots.append(
            ScrapedLot(
                external_id=f"{proc}:lote-{item['n']}:{fname}"[:128],
                title=f"Lote {item['n']} — {item['bens']}"[:512],
                description=item["trecho"],
                category=tipo,
                minimum_bid=item["lance"],
                current_bid=None,
                reference_value=item["avaliacao"],
                url=url,
                raw_data=extra_json(payload),
            )
        )
    return lots


def _money(raw: str) -> float | None:
    try:
        return float(raw.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _one_line(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" .")


def _href(tag: Tag) -> str:
    raw = tag.get("href")
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    return raw if isinstance(raw, str) else ""
