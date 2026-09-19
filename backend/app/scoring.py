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
Laudo antigo também não é preço de mercado: lance acima dele não é overpay;
quanto mais antigo, melhor a oportunidade (juiz só corrige monetariamente).
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Optional

# peso de cada fator quando presente; renormalizado entre os que têm dado
PESO_DESCONTO = 0.26
PESO_JURIDICO = 0.22
PESO_RISCO = 0.12
PESO_DIVIDA = 0.14
PESO_IDADE = 0.12
PESO_PRACA = 0.08
PESO_QUALIDADE = 0.06

TETO_NAO_CITADO = 12
TETO_USUFRUTO = 28
TETO_MEACAO = 28

RE_OCUPADO = re.compile(r"\bocupad[oa]\b", re.I)
RE_DESOCUPADO = re.compile(
    r"\b(?:desocupad[oa]|n[aã]o\s+ocupad[oa]|im[oó]vel\s+vazi[oa])\b",
    re.I,
)
RE_DIVIDA = re.compile(r"d[ií]vida|d[eé]bito|em atraso|inadimpl[êe]nc", re.I)
RE_PRACA = re.compile(r"(\d)\s*[ªa]\s*pra[çc]a", re.I)
RE_CONDO_MENCAO = re.compile(
    r"condom[ií]nio.{0,40}(?:atraso|d[eé]bito|inadimpl|dívida)|"
    r"(?:d[eé]bito|dívida|atraso).{0,30}condom",
    re.I,
)
RE_PRECISA_CONDO = re.compile(
    r"apartamento|cobertura|kitnet|\bflat\b|condom[ií]nio",
    re.I,
)

FONTE_MERCADO = "mercado"
FONTE_LAUDO = "laudo"
FONTE_VENAL = "venal_imovel"


def _brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _money_key(dividas: Optional[dict[str, Any]], key: str) -> float:
    if not isinstance(dividas, dict):
        return 0.0
    raw = dividas.get(key)
    if isinstance(raw, (int, float)) and raw > 0:
        return float(raw)
    return 0.0


def _lance_inicial(current_bid: Optional[float], minimum_bid: Optional[float]) -> Optional[float]:
    """Oferta da praça ativa. Se o atual caiu (2ª praça), usa o atual;
    se subiu (concorrência), o desconto continua pelo inicial."""
    atual = current_bid if current_bid is not None and current_bid > 0 else None
    inicial = minimum_bid if minimum_bid is not None and minimum_bid > 0 else None
    if atual and inicial:
        if atual < inicial * 0.95:
            return atual
        return inicial
    return inicial or atual


def _lance_atual(current_bid: Optional[float], minimum_bid: Optional[float]) -> Optional[float]:
    if current_bid is not None and current_bid > 0:
        return current_bid
    if minimum_bid is not None and minimum_bid > 0:
        return minimum_bid
    return None


def _precisa_condo(tipo: Optional[str], blob: str) -> bool:
    if (tipo or "").lower() in ("apartamento", "sala"):
        return True
    return bool(RE_PRECISA_CONDO.search(blob))


def _anos_avaliacao(avaliacao_data: Optional[Any], hoje: Optional[date] = None) -> Optional[float]:
    quando = _as_date(avaliacao_data)
    if quando is None:
        return None
    return idade_anos(quando, hoje)


def _fator_desconto(
    current_bid: Optional[float],
    minimum_bid: Optional[float],
    reference_value: Optional[float],
    valor_mercado_estimado: Optional[float],
    fonte_avaliacao: Optional[str] = None,
    avaliacao_data: Optional[Any] = None,
    hoje: Optional[date] = None,
) -> tuple[Optional[float], Optional[str], Optional[str]]:
    """Desconto pelo lance inicial. Lance atual acima do inicial não penaliza."""
    lance = _lance_inicial(current_bid, minimum_bid)
    if lance is None or lance <= 0:
        return None, None, None
    if valor_mercado_estimado and valor_mercado_estimado > 0:
        referencia, fonte, rotulo = valor_mercado_estimado, FONTE_MERCADO, "referência de mercado"
    elif reference_value and reference_value > 0:
        fonte = fonte_avaliacao if fonte_avaliacao in (FONTE_LAUDO, FONTE_VENAL) else FONTE_LAUDO
        rotulo = (
            "valor venal do imóvel (IPTU)"
            if fonte == FONTE_VENAL
            else "avaliação"
        )
        referencia = reference_value
    else:
        return None, None, None
    desconto_pct = (referencia - lance) / referencia
    anos = _anos_avaliacao(avaliacao_data, hoje)
    laudo_antigo = fonte == FONTE_LAUDO and anos is not None and anos >= 1
    if fonte == FONTE_VENAL and desconto_pct < 0:
        detalhe = (
            f"lance inicial acima do valor venal do imóvel ({_brl(referencia)}); "
            "venal de IPTU não é preço de mercado — não conta como overpay"
        )
        return None, detalhe, fonte
    if laudo_antigo and desconto_pct < 0:
        n_txt = "1 ano" if round(anos) == 1 else f"{anos:.0f} anos"
        detalhe = (
            f"lance inicial acima da avaliação de {n_txt} ({_brl(referencia)}); "
            "laudo antigo não é preço de mercado — oportunidade, não overpay"
        )
        return None, detalhe, fonte
    nota = max(-1.0, min(1.0, desconto_pct / 0.5))  # 50% de desconto satura a nota
    sinal = "abaixo" if desconto_pct >= 0 else "acima"
    pelo = " (pelo lance inicial)" if (
        current_bid and minimum_bid and current_bid > minimum_bid * 1.05
    ) else ""
    detalhe = f"{abs(desconto_pct) * 100:.0f}% {sinal} da {rotulo}{pelo}"
    return nota, detalhe, fonte


def _alerta_lance_vs_avaliacao(
    current_bid: Optional[float],
    minimum_bid: Optional[float],
    reference_value: Optional[float],
    valor_mercado_estimado: Optional[float],
    fonte_avaliacao: Optional[str] = None,
    avaliacao_data: Optional[Any] = None,
    hoje: Optional[date] = None,
) -> Optional[str]:
    atual = _lance_atual(current_bid, minimum_bid)
    if atual is None:
        return None
    if valor_mercado_estimado and valor_mercado_estimado > 0:
        referencia, rotulo = valor_mercado_estimado, "referência de mercado"
        antigo = False
    elif reference_value and reference_value > 0:
        fonte = fonte_avaliacao if fonte_avaliacao in (FONTE_LAUDO, FONTE_VENAL) else FONTE_LAUDO
        rotulo = "valor venal do imóvel (IPTU)" if fonte == FONTE_VENAL else "avaliação"
        referencia = reference_value
        anos = _anos_avaliacao(avaliacao_data, hoje)
        antigo = fonte == FONTE_LAUDO and anos is not None and anos >= 1
    else:
        return None
    pct = (referencia - atual) / referencia
    inicial = _lance_inicial(current_bid, minimum_bid)
    subiu = bool(inicial and atual > inicial * 1.05)
    if pct >= 0.08 and not subiu:
        return None
    if pct >= 0.08:
        return f"lance atual {_brl(atual)} ainda {pct * 100:.0f}% abaixo da {rotulo}"
    if pct >= 0:
        return f"lance atual {_brl(atual)} já encosta na {rotulo}"
    if antigo:
        anos = _anos_avaliacao(avaliacao_data, hoje) or 0
        n_txt = "1 ano" if round(anos) == 1 else f"{anos:.0f} anos"
        return (
            f"lance atual {_brl(atual)} está {abs(pct) * 100:.0f}% acima da avaliação "
            f"de {n_txt} — laudo defasado, oportunidade, não overpay"
        )
    return f"atenção: lance atual {_brl(atual)} está {abs(pct) * 100:.0f}% acima da {rotulo}"


def _motivo_concorrencia(
    current_bid: Optional[float],
    minimum_bid: Optional[float],
) -> Optional[str]:
    inicial = minimum_bid if minimum_bid and minimum_bid > 0 else None
    atual = current_bid if current_bid and current_bid > 0 else None
    if not inicial or not atual or atual <= inicial * 1.05:
        return None
    pct = (atual - inicial) / inicial * 100
    return (
        f"lance atual {pct:.0f}% acima do inicial — concorrência por oportunidade, "
        "não é ponto negativo"
    )


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
    tipo: Optional[str] = None,
) -> tuple[float, Optional[str]]:
    """Condomínio pesa (não se abate). IPTU em leilão judicial em geral é abatido."""
    lance = _lance_inicial(current_bid, minimum_bid)
    condo = _money_key(dividas, "condominio")
    iptu = _money_key(dividas, "iptu")
    mencao_condo = bool(
        (isinstance(dividas, dict) and dividas.get("mencao_condominio"))
        or RE_CONDO_MENCAO.search(blob)
    )
    precisa = _precisa_condo(tipo, blob)
    iptu_txt = (
        f"IPTU {_brl(iptu)} em geral é abatido na arrematação — não pesa no custo"
        if iptu > 0
        else None
    )
    if (tipo or "").lower() == "terreno":
        if iptu_txt:
            return 0.2, iptu_txt
        return 0.0, None

    if condo > 0 and lance and lance > 0:
        ratio = condo / lance
        detalhe = (
            f"condomínio {_brl(condo)} ({ratio * 100:.1f}% do lance) — "
            "não se abate na arrematação"
        )
        if iptu_txt:
            detalhe = f"{detalhe}. {iptu_txt}"
        if ratio < 0.01:
            return 0.15, detalhe + " (impacto baixo no lance)"
        if ratio < 0.05:
            return -0.25, detalhe
        if ratio < 0.15:
            return -0.7, detalhe + " — peso relevante no custo"
        return -1.0, detalhe + " — dívida alta frente ao lance"

    if mencao_condo:
        detalhe = "menção de débito condominial sem valor consolidado — não se abate na arrematação"
        if iptu_txt:
            detalhe = f"{detalhe}. {iptu_txt}"
        return -0.45, detalhe

    if precisa and condo <= 0 and tem_divida is not False:
        detalhe = (
            "apartamento/casa em condomínio — conferir débitos condominiais "
            "(não se abatem na arrematação)"
        )
        if iptu_txt:
            detalhe = f"{detalhe}. {iptu_txt}"
        return -0.2, detalhe

    if iptu_txt:
        return 0.2, iptu_txt

    if tem_divida is False:
        return 0.4, "sem débitos de condomínio no edital"

    if tem_divida is True or RE_DIVIDA.search(blob):
        if re.search(r"\biptu\b", blob, re.I) and not mencao_condo:
            return 0.2, "menção de IPTU — em leilão judicial costuma ser abatido, não pesa"
        return -0.2, "menção de dívida sem distinguir condomínio/IPTU"
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
            f"processo de {n_txt} ({data_txt}) — oportunidade: "
            "avaliação de referência defasada, abaixo do mercado"
        )
    elif anos >= 10:
        detalhe = (
            f"laudo de {n_txt} ({data_txt}) — forte oportunidade: "
            "juiz em geral só pede correção monetária, abaixo do mercado"
        )
    elif anos >= 5:
        detalhe = (
            f"laudo de {n_txt} ({data_txt}) — oportunidade: "
            "correção monetária costuma ficar abaixo do mercado"
        )
    else:
        detalhe = (
            f"laudo de {n_txt} ({data_txt}) — oportunidade: "
            "já há descompasso frente ao mercado atual"
        )
    return nota, detalhe


def _fator_juridico(riscos: Optional[dict[str, Any]]) -> tuple[Optional[float], list[str]]:
    """Citação, usufruto e meação. Sem dado no PDF o fator fica de fora."""
    if not isinstance(riscos, dict) or not riscos:
        return None, []
    notas: list[float] = []
    motivos: list[str] = []
    citacao = riscos.get("citacao")
    fonte = "DataJud" if riscos.get("citacao_fonte") == "datajud" else "edital"
    if citacao == "nao_citado":
        notas.append(-1.0)
        motivos.append(f"executado não citado ({fonte}) — risco enorme, não entrar")
    elif citacao == "pendente":
        notas.append(-0.85)
        motivos.append(f"citação ainda não cumprida ({fonte}) — não entrar até o dono ser notificado")
    elif citacao == "edital":
        notas.append(-0.7)
        motivos.append(f"citação por edital ({fonte}) — dono pode não ter sido pessoalmente notificado")
    elif citacao == "citado":
        notas.append(0.35)
        motivos.append(f"executado citado ({fonte})")
    if riscos.get("usufruto"):
        notas.append(-0.9)
        motivos.append("usufruto/uso e fruto na matrícula — risco alto (nua propriedade)")
    if riscos.get("meacao"):
        notas.append(-0.85)
        trecho = riscos.get("meacao_trecho")
        if isinstance(trecho, str) and trecho.strip():
            motivos.append(
                f"meação expressa no texto: «{trecho.strip()}» — conferir se o leilão vende 100%"
            )
        else:
            motivos.append("meação expressa no edital — conferir se o leilão vende 100% do imóvel")
    if riscos.get("leiloeiro_ok") is False:
        notas.append(-0.3)
        motivos.append("leiloeiro do edital diverge do anúncio — conferir se é o mesmo processo")
    if riscos.get("docs_limitados"):
        motivos.append(
            "matrícula/laudo sem texto extraível — análise limitada; "
            "não dá para afirmar meação, citação nem ocupação"
        )
    if riscos.get("datajud") in ("nao_encontrado", "indisponivel"):
        motivos.append("DataJud não trouxe movimentos deste processo — citação não confirmada")
    if not notas:
        return None, motivos
    return min(notas), motivos


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
    tipo: Optional[str] = None,
    riscos: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    blob = f"{title} {description or ''}"

    nota_desconto, detalhe_desconto, fonte_usada = _fator_desconto(
        current_bid,
        minimum_bid,
        reference_value,
        valor_mercado_estimado,
        fonte_avaliacao,
        avaliacao_data=avaliacao_data,
        hoje=hoje,
    )
    alerta_lance = _alerta_lance_vs_avaliacao(
        current_bid,
        minimum_bid,
        reference_value,
        valor_mercado_estimado,
        fonte_avaliacao,
        avaliacao_data=avaliacao_data,
        hoje=hoje,
    )
    concorrencia = _motivo_concorrencia(current_bid, minimum_bid)
    limitados = isinstance(riscos, dict) and riscos.get("docs_limitados")
    if limitados:
        nota_risco, detalhe_risco = None, None
        condo_valor = _money_key(dividas, "condominio") if isinstance(dividas, dict) else 0.0
        if condo_valor > 0:
            nota_divida, detalhe_divida = _fator_divida(
                blob,
                tem_divida=True,
                dividas=dividas,
                current_bid=current_bid,
                minimum_bid=minimum_bid,
                tipo=tipo,
            )
        else:
            nota_divida, detalhe_divida = None, None
    else:
        nota_risco, detalhe_risco = _fator_risco(blob, ocupacao=ocupacao)
        nota_divida, detalhe_divida = _fator_divida(
            blob,
            tem_divida=tem_divida,
            dividas=dividas,
            current_bid=current_bid,
            minimum_bid=minimum_bid,
            tipo=tipo,
        )
    nota_idade, detalhe_idade = _fator_idade(
        avaliacao_data, origem=avaliacao_data_origem, hoje=hoje
    )
    nota_praca, detalhe_praca = _fator_praca(blob)
    nota_qualidade, detalhe_qualidade = _fator_qualidade(fonte_usada)
    nota_juridico, motivos_juridico = _fator_juridico(riscos)

    fatores = [
        (PESO_DESCONTO, nota_desconto),
        (PESO_JURIDICO, nota_juridico),
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
    if isinstance(riscos, dict):
        if riscos.get("citacao") in ("nao_citado", "pendente"):
            score = min(score, TETO_NAO_CITADO)
        if riscos.get("usufruto"):
            score = min(score, TETO_USUFRUTO)
        if riscos.get("meacao"):
            score = min(score, TETO_MEACAO)

    motivos = list(motivos_juridico) + [
        d
        for d in (
            detalhe_desconto,
            alerta_lance,
            concorrencia,
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
