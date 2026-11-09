"""
Ledger de indício — vantagem × risco.

Não decide o lance. Aponta se vale aprofundar. Card e dossiê leem o
mesmo objeto. Item sem documento autorizado some; não vira zero.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Optional

from app.gliner_avaliar import ocupacao_se_afirmada
from app.scoring import (
    FONTE_LAUDO,
    FONTE_MERCADO,
    FONTE_VENAL,
    RE_CONDO_MENCAO,
    RE_DESOCUPADO,
    RE_DIVIDA,
    RE_OCUPADO,
    RE_PRACA,
    _alerta_lance_vs_avaliacao,
    _anos_avaliacao,
    _as_date,
    _brl,
    _fator_idade,
    _lance_atual,
    _lance_inicial,
    _money_key,
    _precisa_condo,
    idade_anos,
)

SEM_NORTE = {
    "sem_leitura": "Ainda sem leitura de matrícula, laudo ou penhora. Sem norte.",
    "sem_peca_publica": "Sem matrícula, laudo ou penhora na página pública. Sem norte.",
    "scan_insuficiente": "O scan não rendeu texto útil. Sem norte.",
    "trt_so_edital": "TRT só trouxe edital. Sem matrícula pública, não há norte.",
}
_PECA_TIPOS = ("laudo", "matricula", "penhora")


def motivo_sem_peca(docs: list, source: Optional[str]) -> str:
    """Por que o lote não tem peça útil. Só faz sentido quando a leitura não passou."""
    pecas = [d for d in docs if isinstance(d, dict) and d.get("tipo") in _PECA_TIPOS]
    if pecas and any(d.get("scanned") or int(d.get("chars") or 0) < 80 for d in pecas):
        return "scan_insuficiente"
    if (source or "").lower() == "trt5":
        return "trt_so_edital"
    return "sem_peca_publica"


TETO_NAO_CITADO = 12

# Quem pode afirmar cada linha. Sem fonte desta lista, o item não existe.
DOCUMENTOS: dict[str, tuple[str, ...]] = {
    "veto": ("edital", "datajud"),
    "V1": ("pagina", "laudo", "fipezap", "apify"),
    "V2": ("laudo", "processo"),
    "V3": ("pagina",),
    "V4": ("edital", "matricula", "pagina", "anuncio"),
    "R1": ("edital", "datajud"),
    "R2": ("matricula", "edital"),
    "R3": ("matricula", "edital"),
    "R4": ("edital", "matricula", "pagina", "anuncio"),
    "R5": ("edital", "pagina", "anuncio"),
    "R6": ("edital", "pagina"),
    "R7": ("pagina", "laudo", "fipezap", "apify"),
    "gap": (
        "edital",
        "pagina",
        "laudo",
        "datajud",
        "infosimples",
        "anuncio",
        "nenhuma",
    ),
}

RE_FIDUCIA = re.compile(r"aliena[cç][aã]o\s+fiduci|fiduciante", re.I)
RE_HIPOTECA = re.compile(r"\bhipoteca", re.I)
RE_INDISP = re.compile(r"indisponib", re.I)
RE_FRACAO = re.compile(
    r"fra[cç][aã]o\s+ideal|apenas\s+\d[\d.,]*\s*%|penhora\s+d[ae]\s+\d",
    re.I,
)
RE_EMBARGOS = re.compile(r"embargos?|suspens|acordo", re.I)
RE_MEACAO_PALAVRA = re.compile(r"mea[cç][aã]o|metade\s+(?:do\s+im[oó]vel|da\s+propriedade)", re.I)
RE_MEACAO_PRACA = re.compile(r"50\s*%\s+da\s+avalia", re.I)


def regime_of(
    source: Optional[str] = None,
    origem: Optional[str] = None,
    title: str = "",
    description: Optional[str] = None,
) -> str:
    if (source or "").lower() == "trt5":
        return "trabalhista"
    if origem in ("judicial", "extrajudicial", "trabalhista"):
        return origem
    blob = f"{title} {description or ''}".lower()
    if re.search(r"extrajudicial", blob):
        return "extrajudicial"
    if re.search(r"trabalhista|\btrt\b", blob):
        return "trabalhista"
    if re.search(r"\bjudicial\b", blob):
        return "judicial"
    return "indefinido"


def _item(
    item_id: str,
    lado: str,
    titulo: str,
    *,
    fonte: str,
    frase: str,
    metrica: Optional[str] = None,
    trecho: Optional[str] = None,
    pontos: int = 0,
    confianca: str = "alta",
) -> Optional[dict[str, Any]]:
    allowed = DOCUMENTOS.get(item_id) or DOCUMENTOS["gap"]
    if fonte not in allowed:
        return None
    out: dict[str, Any] = {
        "id": item_id,
        "lado": lado,
        "titulo": titulo,
        "fonte": fonte,
        "frase": frase,
        "pontos": int(pontos),
        "confianca": confianca,
    }
    if metrica:
        out["metrica"] = metrica
    if trecho:
        out["trecho"] = trecho.strip()[:180]
    return out


def _fonte_ocupacao(trechos: Optional[list], default: str) -> str:
    for t in trechos or []:
        if isinstance(t, dict) and t.get("tipo") == "ocupacao":
            origem = t.get("origem")
            if origem in ("edital", "matricula", "pagina", "laudo", "ocr", "anexo"):
                return "edital" if origem in ("laudo", "ocr", "anexo") else str(origem)
    return default


def _ocupacao(
    blob: str,
    ocupacao: Optional[str],
    trechos: Optional[list],
    limitados: bool,
) -> tuple[Optional[str], Optional[str], str]:
    if limitados:
        return None, None, "nenhuma"
    fonte = _fonte_ocupacao(trechos, "edital" if ocupacao else "anuncio")
    trecho = None
    for t in trechos or []:
        if isinstance(t, dict) and t.get("tipo") == "ocupacao" and t.get("texto"):
            trecho = str(t["texto"])
            break
    sit: Optional[str] = None
    trecho_oc: Optional[str] = None
    if ocupacao in ("ocupado", "desocupado"):
        sit, trecho_oc = ocupacao, trecho or ocupacao
    else:
        des = RE_DESOCUPADO.search(blob)
        if des:
            sit, trecho_oc, fonte = "desocupado", des.group(0), "anuncio"
        else:
            occ = RE_OCUPADO.search(blob)
            if occ:
                sit, trecho_oc, fonte = "ocupado", occ.group(0), "anuncio"
    if sit == "ocupado":
        evidencia = blob
        if trecho_oc and trecho_oc.strip().lower() not in ("ocupado", "desocupado"):
            evidencia = f"{blob}\n{trecho_oc}"
        sit = ocupacao_se_afirmada(evidencia, "ocupado")
        if sit is None:
            return None, None, "nenhuma"
    if sit:
        return sit, trecho_oc, fonte
    return None, None, "nenhuma"


def _praca_n(blob: str, pracas: Optional[list]) -> Optional[int]:
    if isinstance(pracas, list) and pracas:
        ativa = next((p for p in pracas if isinstance(p, dict) and p.get("ativa")), None)
        if isinstance(ativa, dict) and isinstance(ativa.get("n"), int):
            return ativa["n"]
        nums = [p.get("n") for p in pracas if isinstance(p, dict) and isinstance(p.get("n"), int)]
        if nums:
            return max(nums)
    matches = [int(m.group(1)) for m in RE_PRACA.finditer(blob)]
    return max(matches) if matches else None


def _pontos_desconto(pct: float) -> int:
    return int(round(max(-20.0, min(20.0, (pct / 0.5) * 20.0))))


def _pontos_idade(anos: float) -> int:
    if anos < 1:
        return int(round(4 * anos))
    if anos < 5:
        return int(round(4 + 5 * (anos - 1) / 4))
    if anos < 10:
        return int(round(9 + 3 * (anos - 5) / 5))
    return 12


def _iptu_frase(regime: str, iptu: float) -> str:
    valor = _brl(iptu) if iptu > 0 else None
    prefixo = f"IPTU {valor}. " if valor else "IPTU. "
    if regime == "judicial":
        return prefixo + "No leilão judicial o tributo anterior sub-roga no preço (Tema 1.134/STJ)."
    if regime == "extrajudicial":
        return prefixo + "No extrajudicial o edital costuma atribuir o IPTU ao arrematante."
    if regime == "trabalhista":
        return prefixo + "Conferir no edital do tribunal — não herdar a regra cível."
    return prefixo + "Sem regime do leilão, não dá para dizer se o IPTU fica com o arrematante."


def compute_ledger(
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
    origem: Optional[str] = None,
    source: Optional[str] = None,
    pracas: Optional[list] = None,
    trechos: Optional[list] = None,
    peticoes: Optional[list] = None,
    valor_m2_fonte: Optional[str] = None,
    avaliado: bool = False,
) -> dict[str, Any]:
    blob = f"{title} {description or ''}"
    riscos = riscos if isinstance(riscos, dict) else {}
    regime = regime_of(source, origem, title, description)
    if regime == "indefinido":
        cnj = riscos.get("processo_cnj")
        if riscos.get("datajud") == "ok" or riscos.get("citacao_fonte") == "datajud":
            regime = "judicial"
        elif isinstance(cnj, str) and cnj.strip() and (source or "").lower() != "trt5":
            regime = "judicial"
    limitados = bool(riscos.get("docs_limitados"))
    itens: list[dict[str, Any]] = []

    def add(item: Optional[dict[str, Any]]) -> None:
        if item:
            itens.append(item)

    # --- Veto / R1 citação ---
    citacao = riscos.get("citacao")
    cit_fonte = "datajud" if riscos.get("citacao_fonte") == "datajud" else "edital"
    if citacao in ("nao_citado", "pendente"):
        add(
            _item(
                "veto",
                "veto",
                "Citação não feita",
                fonte=cit_fonte,
                metrica=citacao,
                frase=(
                    "executado não citado — o arremate não segura."
                    if citacao == "nao_citado"
                    else "Citação ainda não cumprida — não abrir o dossiê como oportunidade."
                ),
                pontos=0,
            )
        )
    elif citacao == "edital":
        add(
            _item(
                "R1",
                "risco",
                "Citação por edital",
                fonte=cit_fonte,
                frase="Citação por edital — o dono pode não ter sido notificado em pessoa.",
                pontos=-12,
            )
        )

    # --- V1 preço ---
    lance = _lance_inicial(current_bid, minimum_bid)
    fonte_preco = None
    ref_preco = None
    rotulo_preco = None
    anos_laudo = _anos_avaliacao(avaliacao_data, hoje)
    laudo_antigo = fonte_avaliacao == FONTE_LAUDO and anos_laudo is not None and anos_laudo >= 1
    mercado_ok = valor_m2_fonte in ("fipezap", "apify") or not valor_m2_fonte
    if valor_mercado_estimado and valor_mercado_estimado > 0 and mercado_ok:
        fonte_preco = valor_m2_fonte if valor_m2_fonte in ("fipezap", "apify") else "fipezap"
        ref_preco = valor_mercado_estimado
        rotulo_preco = "referência de mercado"
    elif reference_value and reference_value > 0 and fonte_avaliacao != FONTE_VENAL and not laudo_antigo:
        fonte_preco = "laudo"
        ref_preco = reference_value
        rotulo_preco = "avaliação"
    v1_pontos = None
    if lance and ref_preco and fonte_preco:
        pct = (ref_preco - lance) / ref_preco
        v1_pontos = _pontos_desconto(pct)
        sinal = "abaixo" if pct >= 0 else "acima"
        extra_oficial = ""
        if (
            valor_mercado_estimado
            and reference_value
            and reference_value > 0
            and fonte_avaliacao != FONTE_VENAL
        ):
            pct_oficial = (reference_value - lance) / reference_value
            extra_oficial = (
                f" Contra a avaliação oficial: {abs(pct_oficial) * 100:.0f}% "
                f"{'abaixo' if pct_oficial >= 0 else 'acima'} "
                "(preço vil mede este número, não o mercado)."
            )
        add(
            _item(
                "V1",
                "vantagem" if (v1_pontos or 0) >= 0 else "risco",
                "Desconto versus referência",
                fonte=fonte_preco,
                metrica=f"{abs(pct) * 100:.0f}% {sinal}",
                frase=f"{abs(pct) * 100:.0f}% {sinal} da {rotulo_preco}.{extra_oficial}",
                pontos=v1_pontos,
            )
        )
    elif lance and reference_value and fonte_avaliacao == FONTE_VENAL:
        add(
            _item(
                "gap",
                "incerteza",
                "Venal de IPTU não compara",
                fonte="pagina",
                frase=(
                    f"Há valor venal do imóvel ({_brl(reference_value)}), mas venal de IPTU "
                    "não é preço de mercado — não conta como overpay."
                ),
            )
        )
    elif lance and reference_value and laudo_antigo:
        pct = (reference_value - lance) / reference_value
        sinal = "abaixo" if pct >= 0 else "acima"
        add(
            _item(
                "V1",
                "vantagem",
                "Desconto versus avaliação oficial",
                fonte="laudo",
                metrica=f"{abs(pct) * 100:.0f}% {sinal}",
                frase=(
                    f"{abs(pct) * 100:.0f}% {sinal} da avaliação de "
                    f"{'1 ano' if round(anos_laudo or 0) == 1 else f'{anos_laudo:.0f} anos'}. "
                    "Laudo velho não é overpay; preço vil ainda mede este número."
                ),
                pontos=0,
            )
        )
    elif lance:
        add(
            _item(
                "gap",
                "incerteza",
                "Sem referência de preço",
                fonte="nenhuma",
                frase="sem referência de preço pra comparar — sem mercado nem laudo usável.",
            )
        )
    else:
        add(
            _item(
                "gap",
                "incerteza",
                "Sem lance publicado",
                fonte="nenhuma",
                frase="Sem lance inicial na página — não há desconto para apontar.",
            )
        )

    # --- V2 idade ---
    quando = _as_date(avaliacao_data)
    if quando is not None:
        anos = idade_anos(quando, hoje)
        if anos >= 1:
            n_txt = "1 ano" if round(anos) == 1 else f"{anos:.0f} anos"
            origem_data = "processo" if avaliacao_data_origem == "processo" else "laudo"
            _, detalhe_idade = _fator_idade(avaliacao_data, origem=avaliacao_data_origem, hoje=hoje)
            add(
                _item(
                    "V2",
                    "vantagem",
                    "Laudo ou processo defasado",
                    fonte=origem_data,
                    metrica=n_txt,
                    frase=detalhe_idade or f"{origem_data} de {n_txt}.",
                    pontos=_pontos_idade(anos),
                )
            )

    # --- V3 praça (prazo, 0 ponto se V1 já usou o lance da praça ativa) ---
    n_praca = _praca_n(blob, pracas)
    if n_praca and n_praca >= 2:
        add(
            _item(
                "V3",
                "vantagem",
                "Praça avançada",
                fonte="pagina",
                metrica=f"{n_praca}ª praça",
                frase=(
                    f"Já na {n_praca}ª praça — prazo mais curto. "
                    "O desconto, se houver, está no lance, não nesta linha."
                ),
                pontos=0,
            )
        )

    # --- V4 / R4 ocupação ---
    sit, trecho_oc, fonte_oc = _ocupacao(blob, ocupacao, trechos, limitados)
    if sit == "desocupado":
        add(
            _item(
                "V4",
                "vantagem",
                "Desocupado",
                fonte=fonte_oc,
                trecho=trecho_oc,
                frase=f"Desocupado no {fonte_oc}: «{trecho_oc}».",
                pontos=6,
            )
        )
    elif sit == "ocupado":
        add(
            _item(
                "R4",
                "risco",
                "Ocupado",
                fonte=fonte_oc,
                trecho=trecho_oc,
                frase=f"Ocupado no {fonte_oc}: «{trecho_oc}» — provável ação de desocupação.",
                pontos=-10,
            )
        )
    elif avaliado:
        add(
            _item(
                "gap",
                "incerteza",
                "Sem ocupação",
                fonte="nenhuma",
                frase="Sem trecho de ocupação — não afirma vazio nem ocupado.",
            )
        )

    # --- R2 usufruto ---
    if riscos.get("usufruto"):
        baixa = riscos.get("usufruto_confianca", "alta") == "baixa"
        trecho_u = riscos.get("usufruto_trecho") if isinstance(riscos.get("usufruto_trecho"), str) else None
        if baixa:
            trecho_u = None
        if baixa and not limitados:
            pass
        else:
            add(
                _item(
                    "R2",
                    "risco",
                    "Usufruto",
                    fonte="edital",
                    trecho=trecho_u,
                    confianca="baixa" if baixa else "alta",
                    frase=(
                        "possível usufruto em cláusula condicional — confirmar na matrícula."
                        if baixa
                        else (
                            f"usufruto na matrícula: «{trecho_u}» — nua propriedade."
                            if trecho_u
                            else "usufruto/uso e fruto na matrícula — nua propriedade."
                        )
                    ),
                    pontos=-6 if baixa else -18,
                )
            )

    # --- R3 o que está à venda ---
    trecho_m = riscos.get("meacao_trecho") if isinstance(riscos.get("meacao_trecho"), str) else None
    meacao_real = bool(riscos.get("meacao"))
    if meacao_real and trecho_m and RE_MEACAO_PRACA.search(trecho_m) and not RE_MEACAO_PALAVRA.search(trecho_m):
        meacao_real = False
    if meacao_real:
        baixa = riscos.get("meacao_confianca", "alta") == "baixa"
        add(
            _item(
                "R3",
                "risco",
                "O que está à venda",
                fonte="edital",
                trecho=trecho_m,
                confianca="baixa" if baixa else "alta",
                frase=(
                    "possível meação em cláusula condicional — confirmar se aplica a este imóvel."
                    if baixa
                    else (
                        f"Meação expressa: «{trecho_m}» — conferir se o leilão vende 100%."
                        if trecho_m
                        else "Meação expressa no edital — conferir se o leilão vende 100%."
                    )
                ),
                pontos=-6 if baixa else -16,
            )
        )
    elif limitados and (RE_FIDUCIA.search(blob) or RE_FRACAO.search(blob)):
        add(
            _item(
                "gap",
                "incerteza",
                "O que está à venda",
                fonte="anuncio",
                frase=(
                    "O anúncio menciona fração ou alienação fiduciária. "
                    "Sem edital/matrícula não dá para afirmar o percentual à venda."
                ),
            )
        )

    # --- R5 condomínio ---
    condo = _money_key(dividas, "condominio")
    iptu = _money_key(dividas, "iptu")
    mencao = bool(
        (isinstance(dividas, dict) and dividas.get("mencao_condominio"))
        or RE_CONDO_MENCAO.search(blob)
    )
    precisa = _precisa_condo(tipo, blob)
    if not limitados or condo > 0:
        if condo > 0 and lance and lance > 0:
            ratio = condo / lance
            if ratio < 0.01:
                pts, extra = -0, " (impacto baixo no lance)"
                # impacto baixo: still a risk line but  -4 is for 1-5%. <1% = -4? 
                # Spec: <1% impacto baixo was +0.15 old. Now 0 or -4?
                # " <1% impacto baixo" in first ledger was slightly positive.
                # Sector: condo is always cost. Use -4 as minimum when we have a number, 
                # except <1% = 0 with phrase impacto baixo.
                pts = 0
            elif ratio < 0.05:
                pts, extra = -4, ""
            elif ratio < 0.15:
                pts, extra = -10, " — peso relevante no custo"
            else:
                pts, extra = -16, " — dívida alta frente ao lance"
            add(
                _item(
                    "R5",
                    "risco" if pts < 0 else "incerteza",
                    "Condomínio",
                    fonte="edital",
                    metrica=f"{ratio * 100:.1f}% do lance",
                    frase=(
                        f"Condomínio {_brl(condo)} ({ratio * 100:.1f}% do lance) — "
                        f"obrigação propter rem; o edital diz se você paga.{extra}"
                    ),
                    pontos=pts,
                )
            )
        elif mencao and not limitados:
            add(
                _item(
                    "R5",
                    "risco",
                    "Condomínio",
                    fonte="anuncio" if RE_CONDO_MENCAO.search(blob) and not (
                        isinstance(dividas, dict) and dividas.get("mencao_condominio")
                    ) else "edital",
                    frase=(
                        "Menção de débito condominial sem valor — obrigação propter rem; "
                        "o edital diz se você paga."
                    ),
                    pontos=-6,
                )
            )
        elif precisa and condo <= 0 and tem_divida is not False and not limitados:
            add(
                _item(
                    "gap",
                    "incerteza",
                    "Apartamento sem valor de condomínio",
                    fonte="nenhuma",
                    frase="Apartamento/sala — falta o valor do condomínio. Não pune no escuro.",
                )
            )
        elif tem_divida is True or (not limitados and RE_DIVIDA.search(blob) and not mencao):
            if re.search(r"\biptu\b", blob, re.I):
                add(
                    _item(
                        "gap",
                        "incerteza",
                        "IPTU",
                        fonte="edital",
                        frase=_iptu_frase(regime, iptu),
                    )
                )
            else:
                add(
                    _item(
                        "gap",
                        "incerteza",
                        "Dívida sem espécie",
                        fonte="anuncio",
                        frase="Há menção de dívida sem distinguir condomínio e IPTU.",
                    )
                )

    if iptu > 0 and not any(i.get("titulo") == "IPTU" for i in itens):
        add(
            _item(
                "gap",
                "incerteza",
                "IPTU",
                fonte="edital",
                metrica=_brl(iptu),
                frase=_iptu_frase(regime, iptu),
            )
        )

    # --- R6 leiloeiro ---
    if riscos.get("leiloeiro_ok") is False:
        add(
            _item(
                "R6",
                "risco",
                "Leiloeiro diverge",
                fonte="edital",
                frase="Leiloeiro do edital diverge do anúncio — conferir se é o mesmo processo.",
                pontos=-4,
            )
        )

    # --- R7 lance atual vs ref recente ---
    alerta = _alerta_lance_vs_avaliacao(
        current_bid,
        minimum_bid,
        reference_value,
        valor_mercado_estimado,
        fonte_avaliacao,
        avaliacao_data=avaliacao_data,
        hoje=hoje,
    )
    atual = _lance_atual(current_bid, minimum_bid)
    ref_recente = None
    if valor_mercado_estimado and valor_mercado_estimado > 0 and (valor_m2_fonte in ("fipezap", "apify") or not valor_m2_fonte):
        ref_recente = valor_mercado_estimado
    elif reference_value and reference_value > 0 and fonte_avaliacao != FONTE_VENAL and not laudo_antigo:
        ref_recente = reference_value
    if atual and ref_recente and alerta and ("acima" in alerta or "encosta" in alerta):
        pct = (ref_recente - atual) / ref_recente
        extra_c = ""
        if current_bid and minimum_bid and current_bid > minimum_bid * 1.05:
            extra_c = " concorrência no lance atual."
        add(
            _item(
                "R7",
                "risco",
                "Lance atual encostou na referência",
                fonte=fonte_preco or "pagina",
                frase=alerta + extra_c,
                pontos=-8 if pct < 0.08 else 0,
            )
        )
    elif alerta:
        extra_c = ""
        if current_bid and minimum_bid and current_bid > minimum_bid * 1.05:
            extra_c = f" Lance {((current_bid - minimum_bid) / minimum_bid) * 100:.0f}% acima do inicial."
        add(
            _item(
                "gap",
                "incerteza",
                "Lance atual versus referência",
                fonte=fonte_preco or "pagina",
                frase=alerta + extra_c,
            )
        )
    elif current_bid and minimum_bid and current_bid > minimum_bid * 1.05:
        pct_c = (current_bid - minimum_bid) / minimum_bid * 100
        add(
            _item(
                "gap",
                "incerteza",
                "Concorrência",
                fonte="pagina",
                metrica=f"{pct_c:.0f}% acima do inicial",
                frase=f"Lance atual {pct_c:.0f}% acima do inicial — contexto, não desconto.",
            )
        )

    # --- gaps de ônus / processo / custo ---
    if limitados:
        add(
            _item(
                "gap",
                "incerteza",
                "Peça sem texto",
                fonte="edital",
                frase="Matrícula/laudo sem texto extraível — análise limitada; não afirma meação, citação nem ocupação.",
            )
        )
    trecho_curto = riscos.get("ocr_curto_trecho") if isinstance(riscos.get("ocr_curto_trecho"), str) else ""
    if riscos.get("ocr_curto") and trecho_curto.strip():
        add(
            _item(
                "gap",
                "incerteza",
                "Leitura curta",
                fonte="edital",
                trecho=trecho_curto.strip()[:220],
                confianca="baixa",
                frase="OCR leu pouco texto. O trecho fica no dossiê, com confiança baixa. Não vira fato.",
            )
        )
    if riscos.get("datajud") in ("nao_encontrado", "indisponivel"):
        add(
            _item(
                "gap",
                "incerteza",
                "DataJud sem movimento",
                fonte="datajud",
                frase="DataJud não trouxe movimentos deste processo — citação não confirmada.",
            )
        )
    if regime == "indefinido" and avaliado:
        add(
            _item(
                "gap",
                "incerteza",
                "Regime do leilão",
                fonte="nenhuma",
                frase="Não dá para dizer se o leilão é judicial, extrajudicial ou trabalhista.",
            )
        )
    if RE_HIPOTECA.search(blob) or RE_INDISP.search(blob):
        qual = "indisponibilidade" if RE_INDISP.search(blob) else "hipoteca"
        add(
            _item(
                "gap",
                "incerteza",
                "Ônus real no texto",
                fonte="anuncio",
                frase=f"Há menção de {qual}. Sem a matrícula não dá para dizer se sobrevive à arrematação.",
            )
        )
    if any(i.get("id") == "V1" for i in itens):
        add(
            _item(
                "gap",
                "incerteza",
                "Custo além do lance",
                fonte="nenhuma",
                frase="Comissão do leiloeiro (cerca de 5%) e ITBI entram no custo e comem o desconto do card.",
            )
        )
    for pet in peticoes or []:
        if not isinstance(pet, dict):
            continue
        tipo_p = str(pet.get("tipo") or "")
        if RE_EMBARGOS.search(tipo_p):
            quando_p = pet.get("data") or ""
            add(
                _item(
                    "gap",
                    "incerteza",
                    "Movimento no processo",
                    fonte="infosimples",
                    frase=f"Há petição «{tipo_p}»{f' em {quando_p}' if quando_p else ''} — não pontua; só avisa.",
                )
            )
            break

    pontos = sum(int(i.get("pontos") or 0) for i in itens)
    score = max(0, min(100, 50 + pontos))
    veto = any(i.get("lado") == "veto" for i in itens)
    if veto:
        score = min(score, TETO_NAO_CITADO)

    risco_duro = any(
        i.get("id") in ("R2", "R3") and i.get("confianca") != "baixa" and (i.get("pontos") or 0) <= -16
        for i in itens
    )
    tem_v = any(i.get("lado") == "vantagem" and (i.get("pontos") or 0) > 0 for i in itens)
    tem_v1 = any(i.get("id") == "V1" and i.get("lado") == "vantagem" for i in itens)

    needed = ["preco", "citacao", "ocupacao"]
    if precisa:
        needed.append("condo")
    have = 0
    if fonte_preco or (laudo_antigo and reference_value):
        have += 1
    if citacao:
        have += 1
    if sit:
        have += 1
    if precisa and (condo > 0 or mencao or tem_divida is False):
        have += 1
    elif precisa:
        pass
    cobertura = have / len(needed) if needed else 1.0

    if veto:
        veredito = "nao_aprofundar"
        titulo = "Não aprofundar"
        corpo = next(
            (i["frase"] for i in itens if i.get("lado") == "veto"),
            "Citação não feita. O arremate não segura.",
        )
    elif risco_duro or (cobertura < 0.5 and not tem_v and not tem_v1):
        veredito = "falta_peca"
        titulo = "Falta peça"
        corpo = next(
            (i["frase"] for i in itens if i.get("id") in ("R2", "R3") and i.get("confianca") != "baixa"),
            next((i["frase"] for i in itens if i.get("lado") == "incerteza"), "Falta documento para afirmar o indício."),
        )
    elif tem_v or tem_v1:
        veredito = "aprofundar"
        titulo = "Aprofundar"
        corpo = next(
            (i["frase"] for i in itens if i.get("lado") == "vantagem"),
            "Há indício de preço ou prazo. Ler o dossiê — não é decisão de lance.",
        )
    else:
        veredito = "falta_peca"
        titulo = "Falta peça"
        corpo = "Não há vantagem com dado. Falta peça para apontar o indício."

    if limitados and veredito != "nao_aprofundar":
        veredito = "falta_peca"
        titulo = "Sem norte"
        corpo = SEM_NORTE.get(str(riscos.get("sem_norte_motivo") or ""), SEM_NORTE["sem_peca_publica"])

    motivos = [i["frase"] for i in itens if i.get("frase")]
    tem_comparacao = bool(fonte_preco and v1_pontos is not None)

    return {
        "score": score,
        "tem_comparacao_preco": tem_comparacao,
        "motivos": motivos,
        "fonte_avaliacao": fonte_preco if fonte_preco in (FONTE_MERCADO, "fipezap", "apify", "laudo") else (
            FONTE_LAUDO if fonte_preco == "laudo" else fonte_preco
        ),
        "veredito": veredito,
        "veredito_titulo": titulo,
        "veredito_corpo": corpo,
        "regime": regime,
        "cobertura": round(cobertura, 2),
        "itens": itens,
    }
