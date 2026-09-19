"""
Consulta paga Infosimples (tribunal/tjsp/primeiro-grau) — só TJSP por ora,
é a única rota validada com resposta real (as demais nunca foram testadas
com token de verdade). R$0,20 por chamada, confirmado num teste real
(header.price="0.2", header.billable=true) — por isso quem decide se roda
é o chamador (orquestrador.py cacheia por processo, não repete a cobrança
numa reavaliação do mesmo lote, e nunca roda no scrape em massa).

Schema real da resposta (verificado em 2026-09-19 contra um processo real
do TJSP): data[0].processos[0] traz classe/foro/vara/juiz, valor_acao e
normalizado_valor_acao (valor da causa/dívida que originou a execução —
não é o valor de avaliação do imóvel), partes (exectdo/reqte/reqdo) e
peticoes_diversas (lista {data, tipo} — sinaliza atividade recente, tipo
"Manifestação do Perito" ou "Pedido de Penhora de Imóvel").
ultimas_movimentacoes costuma vir vazio pra processo antigo — não dá pra
confiar nisso pra citação (mesma limitação já conhecida do DataJud).
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from app.datajud import cnj_digits, tribunal_alias

INFOSIMPLES_URL = "https://api.infosimples.com/api/v2/consultas/tribunal/tjsp/primeiro-grau"
TIMEOUT = 40.0


def _api_token() -> str:
    return os.getenv("INFOSIMPLES_API_TOKEN", "").strip()


def infosimples_disponivel() -> bool:
    return bool(_api_token())


def consultar_infosimples(cnj: str, *, fetch=None) -> dict[str, Any]:
    """Só TJSP (única rota validada). Vazio se faltar token, o processo não
    for TJSP, ou a chamada falhar — nunca inventa dado."""
    token = _api_token()
    if not token or not cnj:
        return {}
    if tribunal_alias(cnj) != "tjsp":
        return {}
    if len(cnj_digits(cnj)) != 20:
        return {}
    params = {"token": token, "processo": cnj}
    try:
        if fetch is not None:
            data = fetch(INFOSIMPLES_URL, params)
        else:
            with httpx.Client(timeout=TIMEOUT) as client:
                r = client.get(INFOSIMPLES_URL, params=params)
                if r.status_code >= 400:
                    return {"infosimples": "indisponivel"}
                data = r.json()
    except Exception:
        return {"infosimples": "indisponivel"}
    if not isinstance(data, dict) or data.get("code") != 200:
        return {"infosimples": "indisponivel"}
    lotes = data.get("data")
    lote = lotes[0] if isinstance(lotes, list) and lotes else None
    processos = lote.get("processos") if isinstance(lote, dict) else None
    proc = processos[0] if isinstance(processos, list) and processos else None
    if not isinstance(proc, dict):
        return {"infosimples": "nao_encontrado"}

    out: dict[str, Any] = {"infosimples": "ok", "infosimples_consultado_para": cnj}
    if proc.get("foro"):
        out["infosimples_foro"] = str(proc["foro"])[:120]
    if proc.get("vara"):
        out["infosimples_vara"] = str(proc["vara"])[:120]
    valor = proc.get("normalizado_valor_acao")
    if isinstance(valor, (int, float)) and valor > 0:
        out["infosimples_valor_causa"] = float(valor)
    peticoes = proc.get("peticoes_diversas")
    if isinstance(peticoes, list) and peticoes:
        recentes = [
            {"data": p.get("data"), "tipo": p.get("tipo")}
            for p in peticoes[-5:]
            if isinstance(p, dict) and p.get("tipo")
        ]
        if recentes:
            out["infosimples_peticoes_recentes"] = recentes
    return out


def merge_infosimples(base: dict[str, Any], info: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key in (
        "infosimples",
        "infosimples_consultado_para",
        "infosimples_foro",
        "infosimples_vara",
        "infosimples_valor_causa",
        "infosimples_peticoes_recentes",
    ):
        if info.get(key) not in (None, "", [], {}):
            out[key] = info[key]
    return out
