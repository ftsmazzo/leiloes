"""
Referência de preço de mercado por cidade, pra comparar com o lance do leilão.

Fonte: Índice FipeZap de Venda Residencial (Fipe + Grupo OLX). Preço médio
pedido de apartamento pronto, 56 cidades. Não é transação (ITBI) e não cobre
interior fino (Brodowski, Formiga, Tietê…). Cidade ausente = sem dado —
nunca ler como desconto zero.

Informe: agosto/2026
https://downloads.fipe.org.br/indices/fipezap/fipezap-202608-residencial-venda.pdf
"""
from __future__ import annotations

import re
from typing import Any, Optional, Union

FIPEZAP_MES = "2026-08"
FIPEZAP_URL = (
    "https://downloads.fipe.org.br/indices/fipezap/fipezap-202608-residencial-venda.pdf"
)

# cidade (sem acento, minúscula) -> R$/m²
PRICE_PER_M2_BY_CIDADE: dict[str, float] = {
    "aracaju": 5826.0,
    "balneario camboriu": 15343.0,
    "barueri": 12206.0,
    "belem": 8843.0,
    "belo horizonte": 10667.0,
    "betim": 5087.0,
    "blumenau": 8177.0,
    "brasilia": 10369.0,
    "distrito federal": 10369.0,
    "campinas": 8089.0,
    "campo grande": 6830.0,
    "canoas": 5950.0,
    "caxias do sul": 6463.0,
    "contagem": 6210.0,
    "cuiaba": 7044.0,
    "curitiba": 11731.0,
    "diadema": 6936.0,
    "florianopolis": 13531.0,
    "fortaleza": 9502.0,
    "goiania": 8482.0,
    "guaruja": 7035.0,
    "guarulhos": 7527.0,
    "itajai": 13354.0,
    "itapema": 15403.0,
    "jaboatao dos guararapes": 6485.0,
    "joao pessoa": 8387.0,
    "joinville": 8389.0,
    "londrina": 5856.0,
    "maceio": 9974.0,
    "manaus": 7884.0,
    "natal": 6439.0,
    "niteroi": 8057.0,
    "novo hamburgo": 5367.0,
    "osasco": 8668.0,
    "pelotas": 4647.0,
    "porto alegre": 7510.0,
    "praia grande": 6814.0,
    "recife": 8912.0,
    "ribeirao preto": 5344.0,
    "rio de janeiro": 11216.0,
    "salvador": 8653.0,
    "santa maria": 5514.0,
    "santo andre": 7951.0,
    "santos": 8547.0,
    "sao bernardo do campo": 7444.0,
    "sao caetano do sul": 9704.0,
    "sao jose": 9093.0,
    "sao jose do rio preto": 6056.0,
    "sao jose dos campos": 9615.0,
    "sao jose dos pinhais": 6367.0,
    "sao leopoldo": 5200.0,
    "sao luis": 8829.0,
    "sao paulo": 12143.0,
    "sao vicente": 5118.0,
    "teresina": 6032.0,
    "vila velha": 11446.0,
    "vitoria": 15650.0,
}

# FipeZap mede apto pronto. Esses tipos não entram na média.
TIPOS_SEM_FIPEZAP = frozenset({"terreno", "galpao", "chacara", "sala", "veiculo"})

_ACCENT = str.maketrans(
    "áàâãäéèêëíìîïóòôõöúùûüçÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ",
    "aaaaaeeeeiiiiooooouuuucAAAAAEEEEIIIIOOOOOUUUUC",
)

_RE_AREA_NUM = re.compile(r"([\d.,]+)")

# Teto pra não multiplicar FipeZap por área de terreno/condomínio lida errada.
_MAX_M2_RESIDENCIAL = {
    "apartamento": 400.0,
    "sala": 400.0,
    "casa": 800.0,
    "chacara": 5000.0,
    "imovel": 800.0,
}


def _fold(text: str) -> str:
    return text.translate(_ACCENT).strip().lower()


def price_per_m2(cidade: Optional[str]) -> Optional[float]:
    """R$/m² do FipeZap pra cidade, ou None se não tiver referência."""
    if not cidade:
        return None
    return PRICE_PER_M2_BY_CIDADE.get(_fold(cidade))


def _parse_area_number(raw: str) -> Optional[float]:
    """'76,7508' → 76.7508; '1.234,56' → 1234.56; '1.234' → 1234; '59' → 59."""
    text = (raw or "").strip()
    if not text:
        return None
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif text.count(".") > 1:
        text = text.replace(".", "")
    elif re.fullmatch(r"\d{1,3}\.\d{3}", text):
        # 6.908 em texto BR quase sempre é milhar (6908), não 6,908 m².
        text = text.replace(".", "")
    try:
        value = float(text)
    except ValueError:
        return None
    return value if value > 0 else None


def _area_m2(area: Optional[Union[str, int, float]]) -> Optional[float]:
    """Número de '500 m²' ou float já extraído."""
    if isinstance(area, (int, float)):
        return float(area) if area > 0 else None
    if not area:
        return None
    match = _RE_AREA_NUM.search(str(area))
    if not match:
        return None
    return _parse_area_number(match.group(1))


def estimate_market_value(
    cidade: Optional[str],
    area: Optional[Union[str, int, float]],
    tipo: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """valor_mercado_estimado = preço/m² FipeZap × área.

    None se a cidade não está no índice, se falta área, se o tipo
    não é o que o FipeZap mede (terreno, galpão, etc.), ou se a área
    extrapola o que faz sentido pro tipo (ex.: 6908 m² num apartamento).
    """
    kind = (tipo or "").lower()
    if kind in TIPOS_SEM_FIPEZAP:
        return None
    ppm2 = price_per_m2(cidade)
    area_m2 = _area_m2(area)
    if ppm2 is None or area_m2 is None:
        return None
    teto = _MAX_M2_RESIDENCIAL.get(kind, 800.0)
    if area_m2 > teto:
        return None
    return {
        "valor_m2_regiao": ppm2,
        "valor_mercado_estimado": round(ppm2 * area_m2, 2),
        "valor_m2_fonte": "fipezap",
        "valor_m2_mes": FIPEZAP_MES,
    }
