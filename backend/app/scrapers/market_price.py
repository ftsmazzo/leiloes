"""
Referência de preço de mercado por cidade, pra comparar com o lance do leilão.

MVP deliberadamente manual: o Índice FipeZap (a fonte nacional mais citável)
só cobre 56 cidades, quase todas capitais — não cobre o interior, que é onde
a maioria dos leilões deste catálogo acontece (Formiga-MG, Tietê-SP,
Guarujá-SP, Lorena-SP, Sertãozinho-SP, Santa Rosa de Viterbo-SP, ...).
Não tem fonte pública confiável e gratuita pra preço/m² dessas cidades.

Por isso a tabela abaixo começa quase vazia — só com um valor de fonte
oficial, de exemplo, pra mostrar o formato. Preencha com número que você
confia pra cada cidade que importa pro seu catálogo (corretor local, anúncio
comparável, etc.). Cidade ausente da tabela = sem referência de mercado —
NUNCA leia isso como "sem desconto"; é dado faltando, não desconto zero.
"""
from __future__ import annotations

import re
from typing import Any, Optional

# cidade (sem acento, minúscula) -> R$/m²
PRICE_PER_M2_BY_CIDADE: dict[str, float] = {
    # Índice FipeZap de Venda Residencial, junho/2026 — única cidade do
    # catálogo hoje coberta por uma fonte nacional. Substitua/complete com
    # as cidades reais dos seus leilões.
    # https://downloads.fipe.org.br/indices/fipezap/fipezap-202606-residencial-venda.pdf
    "sao paulo": 12055.0,
}

_ACCENT = str.maketrans(
    "áàâãäéèêëíìîïóòôõöúùûüçÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ",
    "aaaaaeeeeiiiiooooouuuucAAAAAEEEEIIIIOOOOOUUUUC",
)

_RE_AREA_NUM = re.compile(r"([\d.,]+)")


def _fold(text: str) -> str:
    return text.translate(_ACCENT).strip().lower()


def price_per_m2(cidade: Optional[str]) -> Optional[float]:
    """R$/m² cadastrado pra cidade, ou None se não tiver referência."""
    if not cidade:
        return None
    return PRICE_PER_M2_BY_CIDADE.get(_fold(cidade))


def _area_m2(area: Optional[str]) -> Optional[float]:
    """Extrai o número de uma string tipo '500 m²' (formato de extract.area_from_text)."""
    if not area:
        return None
    match = _RE_AREA_NUM.search(area)
    if not match:
        return None
    raw = match.group(1).replace(".", "").replace(",", ".")
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def estimate_market_value(cidade: Optional[str], area: Optional[str]) -> Optional[dict[str, Any]]:
    """valor_mercado_estimado = preço/m² da cidade × área do lote.

    Retorna None quando falta cidade cadastrada na tabela OU área numérica —
    o chamador não deve tratar None como "sem desconto", e sim "sem dado".
    """
    ppm2 = price_per_m2(cidade)
    area_m2 = _area_m2(area)
    if ppm2 is None or area_m2 is None:
        return None
    return {
        "valor_m2_regiao": ppm2,
        "valor_mercado_estimado": round(ppm2 * area_m2, 2),
    }
