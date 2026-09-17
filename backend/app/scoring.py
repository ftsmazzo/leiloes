"""
Score de oportunidade por lote (0-100) + motivos, calculado a partir do que
já está disponível: desconto vs. referência de preço (quando existe — ver
market_price.py, cobertura ainda pequena de propósito), ocupação, dívidas
com valor, idade do laudo (antigo = oportunidade), avanço de praça e
qualidade da fonte (laudo vs. venal de IPTU).

Decisão de produto (conversa com o dono do catálogo): quando falta
referência de preço — hoje a maioria dos lotes, só ~7% têm avaliação do
edital e a tabela de mercado cobre 1 cidade — o score NÃO vira "sem
desconto". O fator de desconto fica de fora do cálculo (não conta como
nota zero) e um aviso explícito (`tem_comparacao_preco=False`) avisa que
o número é parcial, calculado só com os fatores que têm dado.

Valor venal de IPTU não é laudo de mercado: lance acima do venal é comum
e não conta como overpay. Lance abaixo do venal ainda é sinal positivo.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Optional

# peso de cada fator quando presente; renormalizado entre os que têm dado
PESO_DESCONTO = 0.32
PESO_RISCO = 0.18
PESO_DIVIDA = 0.17
PESO_IDADE = 0.15
PESO_PRACA = 0.10
PESO_QUALIDADE = 0.08

RE_OCUPADO = re.compile(r"\bocupad[oa]\b", re.I)
RE_DESOCUPADO = re.compile(r"\b(?:des|não\s+)ocupad[oa]|\blivre\b|\bvazi[oa]\b", re.I)
RE_DIVIDA = re.compile(r"d[ií]vida|d[eé]bito|em atraso|inadimpl[êe]nc", re.I)
RE_PRACA = re.compile(r"(\d)\s*[ªa]\s*pra[çc]a", re.I)

FONTE_MERCADO = "mercado"
FONTE_LAUDO = "laudo"
FONTE_VENAL = "venal_imovel"


def _brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _total_dividas(dividas: Optional[dict[str, Any]]) -> float:
    if not isinstance(dividas, dict):
        return 0.0
    total = 0.0
    for key in ("iptu", "condominio"):
        raw = dividas.get(key)
        if isinstance(raw, (int, float)) and raw > 0:
            total += float(raw)
    return total


def _fator_desconto(
    current_bid: Optional[float],
    minimum_bid: Optional[float],
    reference_value: Optional[float],
    valor_mercado_estimado: Optional[float],
    fonte_avaliacao: Optional[str] = None,
) -> tuple[Optional[float], Optional[str], Optional[str]]:
    """nota, detalhe, fonte usada (mercado/laudo/venal_imovel)."""
    lance = current_bid if current_bid is not None else minimum_bid
    if lance is None or lance <= 0:
        return None, None, None
    if valor_mercado_estimado and valor_mercado_estimado > 0:
        referencia, fonte, rotulo = valor_mercado_estimado, FONTE_MERCADO, "referência de mercado"
    elif reference_value and reference_value > 0:
        fonte = fonte_avaliacao if fonte_avaliacao in (FONTE_LAUDO, FONTE_VENAL) else FONTE_LAUDO
        rotulo = (
            "valor venal do imóvel (IPTU)"
            if fonte == FONTE_VENAL
            else "avaliação do edital"
        )
        referencia = reference_value
    else:
        return None, None, None
    desconto_pct = (referencia - lance) / referencia
    if fonte == FONTE_VENAL and desconto_pct < 0:
        detalhe = (
            f"lance acima do valor venal do imóvel ({_brl(referencia)}); "
            "venal de IPTU não é preço de mercado — não conta como overpay"
        )
        return None, detalhe, fonte
    nota = max(-1.0, min(1.0, desconto_pct / 0.5))  # 50% de desconto satura a nota
    sinal = "abaixo" if desconto_pct >= 0 else "acima"
    detalhe = f"{abs(desconto_pct) * 100:.0f}% {sinal} da {rotulo}"
    return nota, detalhe, fonte


def _fator_risco(
    blob: str,
    ocupacao: Optional[str] = None,
) -> tuple[float, str]:
    if ocupacao == "desocupado":
        desocupado, ocupado = True, False
    elif ocupacao == "ocupado":
        desocupado, ocupado = False, True
    else:
        desocupado = bool(RE_DESOCUPADO.search(blob))
        ocupado = bool(RE_OCUPADO.search(blob)) and not desocupado
    fonte_risco = "edital" if ocupacao else "anúncio"
    if ocupado:
        return -0.6, f"ocupado — provável ação de desocupação ({fonte_risco})"
    if desocupado:
        return 0.4, f"desocupado (declarado no {fonte_risco})"
    return 0.0, "sem menção de ocupação — verificar edital"


def _fator_divida(
    blob: str,
    *,
    tem_divida: Optional[bool] = None,
    dividas: Optional[dict[str, Any]] = None,
    current_bid: Optional[float] = None,
    minimum_bid: Optional[float] = None,
) -> tuple[float, str]:
    lance = current_bid if current_bid is not None else minimum_bid
    total = _total_dividas(dividas)
    if tem_divida is False and total <= 0:
        return 0.4, "sem débitos relevantes no edital"
    if total > 0 and lance and lance > 0:
        ratio = total / lance
        detalhe = f"débitos {_brl(total)} ({ratio * 100:.1f}% do lance)"
        if ratio < 0.01:
            return 0.2, detalhe + " — impacto baixo no lance"
        if ratio < 0.05:
            return -0.2, detalhe
        if ratio < 0.15:
            return -0.6, detalhe + " — peso relevante no custo"
        return -1.0, detalhe + " — dívida alta frente ao lance"
    if tem_divida is True or (tem_divida is None and RE_DIVIDA.search(blob)):
        return -0.35, "menção de dívida/débito sem valor consolidado"
    return 0.0, None


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


def _as_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and len(value) >= 10:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def idade_anos(quando: date, hoje: Optional[date] = None) -> float:
    """Anos civis + fração. 17/09/2016 → 17/09/2026 = 10, não 9,99 por bissexto."""
    ref = hoje or date.today()
    if ref < quando:
        return 0.0
    cheios = ref.year - quando.year
    if (ref.month, ref.day) < (quando.month, quando.day):
        cheios -= 1
    try:
        aniversario = quando.replace(year=quando.year + cheios)
    except ValueError:
        aniversario = date(quando.year + cheios, 3, 1)
    fracao = (ref - aniversario).days / 365.25
    return max(0.0, cheios + fracao)


def _fator_idade(
    avaliacao_data: Optional[Any] = None,
    origem: Optional[str] = None,
    hoje: Optional[date] = None,
) -> tuple[Optional[float], Optional[str]]:
    """Laudo/processo antigo = oportunidade: juiz costuma só corrigir monetariamente."""
    quando = _as_date(avaliacao_data)
    if quando is None:
        return None, None
    anos = idade_anos(quando, hoje)
    if anos < 1:
        nota = 0.35 * anos
    elif anos < 5:
        nota = 0.35 + 0.40 * (anos - 1) / 4
    elif anos < 10:
        nota = 0.75 + 0.25 * (anos - 5) / 5
    else:
        nota = 1.0
    n_txt = "1 ano" if round(anos) == 1 else f"{anos:.0f} anos"
    data_txt = quando.strftime("%m/%Y")
    if origem == "processo":
        detalhe = (
            f"processo de {n_txt} ({data_txt}) — tramitação longa; "
            "avaliação de referência tende a ficar defasada"
        )
    elif anos >= 10:
        detalhe = (
            f"laudo de {n_txt} ({data_txt}) — forte oportunidade: "
            "juiz em geral só pede correção monetária, abaixo do mercado"
        )
    elif anos >= 5:
        detalhe = (
            f"laudo de {n_txt} ({data_txt}) — correção monetária costuma ficar abaixo do mercado"
        )
    else:
        detalhe = (
            f"laudo de {n_txt} ({data_txt}) — já há descompasso frente ao mercado atual"
        )
    return nota, detalhe


def _fator_qualidade(fonte: Optional[str]) -> tuple[Optional[float], Optional[str]]:
    if fonte == FONTE_MERCADO:
        return 0.7, "comparação com preço de mercado da região"
    if fonte == FONTE_LAUDO:
        return 0.4, "comparação com laudo/avaliação do processo"
    if fonte == FONTE_VENAL:
        return -0.3, "só há valor venal de IPTU — costuma ficar abaixo do mercado"
    return None, None


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
    fonte_avaliacao: Optional[str] = None,
    dividas: Optional[dict[str, Any]] = None,
    avaliacao_data: Optional[Any] = None,
    avaliacao_data_origem: Optional[str] = None,
    hoje: Optional[date] = None,
) -> dict[str, Any]:
    blob = f"{title} {description or ''}"

    nota_desconto, detalhe_desconto, fonte_usada = _fator_desconto(
        current_bid,
        minimum_bid,
        reference_value,
        valor_mercado_estimado,
        fonte_avaliacao,
    )
    nota_risco, detalhe_risco = _fator_risco(blob, ocupacao=ocupacao)
    nota_divida, detalhe_divida = _fator_divida(
        blob,
        tem_divida=tem_divida,
        dividas=dividas,
        current_bid=current_bid,
        minimum_bid=minimum_bid,
    )
    nota_idade, detalhe_idade = _fator_idade(
        avaliacao_data, origem=avaliacao_data_origem, hoje=hoje
    )
    nota_praca, detalhe_praca = _fator_praca(blob)
    nota_qualidade, detalhe_qualidade = _fator_qualidade(fonte_usada)

    fatores = [
        (PESO_DESCONTO, nota_desconto),
        (PESO_RISCO, nota_risco),
        (PESO_DIVIDA, nota_divida),
        (PESO_IDADE, nota_idade),
        (PESO_PRACA, nota_praca),
        (PESO_QUALIDADE, nota_qualidade),
    ]
    presentes = [(peso, nota) for peso, nota in fatores if nota is not None]
    peso_total = sum(peso for peso, _ in presentes) or 1.0
    media = sum(peso * nota for peso, nota in presentes) / peso_total
    score = round((media + 1) / 2 * 100)
    score = max(0, min(100, score))

    motivos = [
        d
        for d in (
            detalhe_desconto,
            detalhe_risco,
            detalhe_divida,
            detalhe_idade,
            detalhe_praca,
            detalhe_qualidade,
        )
        if d
    ]
    tem_comparacao_preco = fonte_usada in (FONTE_MERCADO, FONTE_LAUDO) and nota_desconto is not None
    if fonte_usada is None:
        motivos.insert(0, "sem referência de preço pra comparar — score calculado só com risco/praça")

    return {
        "score": score,
        "tem_comparacao_preco": tem_comparacao_preco,
        "motivos": motivos,
        "fonte_avaliacao": fonte_usada,
    }
