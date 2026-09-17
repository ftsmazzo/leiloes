"""
Score de oportunidade por lote (0-100) + motivos, calculado a partir do que
já está disponível: desconto vs. referência de preço (quando existe — ver
market_price.py, cobertura ainda pequena de propósito), menção de
ocupação/dívida no anúncio, e avanço de praça.

Decisão de produto (conversa com o dono do catálogo): quando falta
referência de preço — hoje a maioria dos lotes, só ~7% têm avaliação do
edital e a tabela de mercado cobre 1 cidade — o score NÃO vira "sem
desconto". O fator de desconto fica de fora do cálculo (não conta como
nota zero) e um aviso explícito (`tem_comparacao_preco=False`) avisa que
o número é parcial, calculado só com os fatores que têm dado.
"""
from __future__ import annotations

import re
from typing import Any, Optional

# peso de cada fator quando presente; renormalizado entre os que têm dado
PESO_DESCONTO = 0.60
PESO_RISCO = 0.25
PESO_PRACA = 0.15

RE_OCUPADO = re.compile(r"\bocupad[oa]\b", re.I)
RE_DESOCUPADO = re.compile(r"\b(?:des|não\s+)ocupad[oa]|\blivre\b|\bvazi[oa]\b", re.I)
RE_DIVIDA = re.compile(r"d[ií]vida|d[eé]bito|em atraso|inadimpl[êe]nc", re.I)
RE_PRACA = re.compile(r"(\d)\s*[ªa]\s*pra[çc]a", re.I)


def _fator_desconto(
    current_bid: Optional[float],
    minimum_bid: Optional[float],
    reference_value: Optional[float],
    valor_mercado_estimado: Optional[float],
) -> tuple[Optional[float], Optional[str]]:
    lance = current_bid if current_bid is not None else minimum_bid
    if lance is None or lance <= 0:
        return None, None
    if valor_mercado_estimado and valor_mercado_estimado > 0:
        referencia, fonte = valor_mercado_estimado, "referência de mercado"
    elif reference_value and reference_value > 0:
        referencia, fonte = reference_value, "avaliação do edital"
    else:
        return None, None
    desconto_pct = (referencia - lance) / referencia
    nota = max(-1.0, min(1.0, desconto_pct / 0.5))  # 50% de desconto satura a nota
    sinal = "abaixo" if desconto_pct >= 0 else "acima"
    detalhe = f"{abs(desconto_pct) * 100:.0f}% {sinal} da {fonte}"
    return nota, detalhe


def _fator_risco(
    blob: str,
    ocupacao: Optional[str] = None,
    tem_divida: Optional[bool] = None,
) -> tuple[float, str]:
    if ocupacao == "desocupado":
        desocupado, ocupado = True, False
    elif ocupacao == "ocupado":
        desocupado, ocupado = False, True
    else:
        desocupado = bool(RE_DESOCUPADO.search(blob))
        ocupado = bool(RE_OCUPADO.search(blob)) and not desocupado
    if tem_divida is True:
        divida = True
    elif tem_divida is False:
        divida = False
    else:
        divida = bool(RE_DIVIDA.search(blob))
    fonte_risco = "edital" if ocupacao or tem_divida is not None else "anúncio"
    if ocupado and divida:
        return -1.0, f"ocupado e com menção de dívida — risco jurídico alto ({fonte_risco})"
    if ocupado:
        return -0.6, f"ocupado — provável ação de desocupação ({fonte_risco})"
    if divida:
        return -0.4, f"menção de dívida/débito no {fonte_risco}"
    if desocupado:
        return 0.3, f"desocupado (declarado no {fonte_risco})"
    return 0.0, "sem menção de ocupação/dívida — verificar edital"


def _fator_praca(blob: str) -> tuple[float, Optional[str]]:
    matches = [int(m.group(1)) for m in RE_PRACA.finditer(blob)]
    if not matches:
        return 0.0, None
    n = max(matches)
    if n <= 1:
        return 0.0, None
    if n == 2:
        return 0.5, "já na 2ª praça — desconto judicial maior, mas prazo mais curto"
    return 1.0, f"já na {n}ª praça — desconto judicial grande, atenção ao prazo"


def compute_score(
    *,
    title: str,
    description: Optional[str] = None,
    current_bid: Optional[float] = None,
    minimum_bid: Optional[float] = None,
    reference_value: Optional[float] = None,
    valor_mercado_estimado: Optional[float] = None,
    ocupacao: Optional[str] = None,
    tem_divida: Optional[bool] = None,
) -> dict[str, Any]:
    blob = f"{title} {description or ''}"

    nota_desconto, detalhe_desconto = _fator_desconto(
        current_bid, minimum_bid, reference_value, valor_mercado_estimado
    )
    nota_risco, detalhe_risco = _fator_risco(blob, ocupacao=ocupacao, tem_divida=tem_divida)
    nota_praca, detalhe_praca = _fator_praca(blob)

    fatores = [(PESO_DESCONTO, nota_desconto), (PESO_RISCO, nota_risco), (PESO_PRACA, nota_praca)]
    presentes = [(peso, nota) for peso, nota in fatores if nota is not None]
    peso_total = sum(peso for peso, _ in presentes) or 1.0
    media = sum(peso * nota for peso, nota in presentes) / peso_total
    score = round((media + 1) / 2 * 100)
    score = max(0, min(100, score))

    motivos = [d for d in (detalhe_desconto, detalhe_risco, detalhe_praca) if d]
    tem_comparacao_preco = nota_desconto is not None
    if not tem_comparacao_preco:
        motivos.insert(0, "sem referência de preço pra comparar — score calculado só com risco/praça")

    return {
        "score": score,
        "tem_comparacao_preco": tem_comparacao_preco,
        "motivos": motivos,
    }
