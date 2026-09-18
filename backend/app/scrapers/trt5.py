"""
TRT5 (Tribunal Regional do Trabalho da 5ª Região, BA) — editais de alienação
judicial por iniciativa particular, publicados direto pelo tribunal.
Página pública, sem login. Só pega "Edital de Alienação" (PDF de um imóvel
só) — "Leilão Unificado" (vários imóveis de vários leiloeiros num PDF só)
fica de fora por ora: exigiria abrir e separar o PDF em lotes, tarefa maior.
"""
from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup, Tag

from .base import BaseScraper, ScrapedAuction, ScrapedLot
from .listing import HEADERS, abs_url, cidade_from_text, extra_lot, tipo_from_text

RE_ALIENACAO = re.compile(r"edital\s+de\s+aliena[cç][aã]o", re.I)
RE_PROCESSO = re.compile(r"(?:PROCESSO|REEF)\s*[:.]?\s*([\d./-]{8,30})", re.I)


class Trt5Scraper(BaseScraper):
    source_name = "trt5"
    base_url = "https://www.trt5.jus.br"

    async def scrape(self) -> list[ScrapedAuction]:
        by_id: dict[str, ScrapedLot] = {}
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
                if not found or new == 0:
                    break
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


def _href(tag: Tag) -> str:
    raw = tag.get("href")
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    return raw if isinstance(raw, str) else ""
