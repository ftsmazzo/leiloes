"""Monta DTOs da API a partir dos modelos persistidos."""
from __future__ import annotations

from typing import Any

from app.api.schemas import LotOut
from app.edital import parecer_from_facts
from app.models.schemas import LotModel
from app.search import cidade_of, endereco_of, foto_of, raw_dict, tipo_of
from app.scrapers.extract import format_card, tipo_from_text
from app.scrapers.listing import merge_pracas
from app.ledger import SEM_NORTE
from app.scoring import compute_score


def _ocupacao_do_ledger(ledger: object, stored: str | None) -> str | None:
    itens = ledger if isinstance(ledger, list) else []
    if any(isinstance(i, dict) and i.get("id") == "V4" for i in itens):
        return "desocupado"
    if any(isinstance(i, dict) and i.get("id") == "R4" for i in itens):
        return "ocupado"
    if any(isinstance(i, dict) and i.get("titulo") == "Sem ocupação" for i in itens):
        return None
    return stored


def _riscos_para_ledger(raw: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any] | None:
    base = extra.get("riscos") if isinstance(extra.get("riscos"), dict) else raw.get("riscos")
    riscos = dict(base) if isinstance(base, dict) else {}
    datajud = extra.get("datajud") or raw.get("datajud")
    if isinstance(datajud, str) and datajud:
        riscos.setdefault("datajud", datajud)
    cnj = extra.get("processo_cnj") or raw.get("processo_cnj")
    if isinstance(cnj, str) and cnj.strip():
        riscos.setdefault("processo_cnj", cnj)
    if extra.get("docs_limitados") or raw.get("docs_limitados"):
        riscos["docs_limitados"] = True
    motivo = extra.get("sem_norte_motivo") or raw.get("sem_norte_motivo")
    if isinstance(motivo, str) and motivo:
        riscos["sem_norte_motivo"] = motivo
    return riscos or None


def _pracas_out(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        return []
    return merge_pracas([], raw)


def _hydrate_ledger(
    lot: LotModel,
    source: str,
    raw: dict[str, Any],
    extra: dict[str, Any],
    tipo: str | None,
    current_bid: float | None,
    reference_value: float | None,
) -> dict[str, Any]:
    """Ledger é derivado dos campos atuais — não congela frase velha."""
    info = compute_score(
        title=getattr(lot, "title", None) or "",
        description=getattr(lot, "description", None),
        current_bid=current_bid,
        minimum_bid=lot.minimum_bid,
        reference_value=reference_value,
        valor_mercado_estimado=extra.get("valor_mercado_estimado")
        if isinstance(extra.get("valor_mercado_estimado"), (int, float))
        else None,
        ocupacao=extra.get("ocupacao") if extra.get("ocupacao") in ("ocupado", "desocupado") else None,
        tem_divida=True if extra.get("dividas") else extra.get("tem_divida") if isinstance(extra.get("tem_divida"), bool) else None,
        fonte_avaliacao=extra.get("avaliacao_fonte") if extra.get("avaliacao_fonte") in ("laudo", "venal_imovel") else None,
        dividas=extra.get("dividas") if isinstance(extra.get("dividas"), dict) else None,
        avaliacao_data=extra.get("avaliacao_data"),
        avaliacao_data_origem=extra.get("avaliacao_data_origem")
        if extra.get("avaliacao_data_origem") in ("laudo", "processo")
        else None,
        tipo=tipo,
        riscos=_riscos_para_ledger(raw, extra),
        origem=extra.get("origem") if isinstance(extra.get("origem"), str) else None,
        source=source,
        pracas=_pracas_out(extra.get("pracas") or raw.get("pracas")),
        trechos=extra.get("trechos") if isinstance(extra.get("trechos"), list) else None,
        peticoes=extra.get("infosimples_peticoes_recentes")
        if isinstance(extra.get("infosimples_peticoes_recentes"), list)
        else None,
        valor_m2_fonte=extra.get("valor_m2_fonte") if isinstance(extra.get("valor_m2_fonte"), str) else None,
        avaliado=bool(extra.get("avaliado_em")),
    )
    return {
        "score": info["score"],
        "score_tem_comparacao_preco": info["tem_comparacao_preco"],
        "score_motivos": info["motivos"],
        "veredito": info.get("veredito"),
        "veredito_titulo": info.get("veredito_titulo"),
        "veredito_corpo": info.get("veredito_corpo"),
        "regime": info.get("regime"),
        "cobertura": info.get("cobertura"),
        "ledger": info.get("itens") or [],
    }


def lot_to_out(lot: LotModel, source: str) -> LotOut:
    raw = raw_dict(lot)
    extra = format_card(
        getattr(lot, "title", None) or "",
        getattr(lot, "description", None),
        raw,
    )
    tipo = extra.get("tipo") or tipo_of(lot) or tipo_from_text(getattr(lot, "title", None), getattr(lot, "category", None))
    current_bid = (
        extra.get("lance_pagina")
        if isinstance(extra.get("lance_pagina"), (int, float))
        else lot.current_bid
    )
    reference_value = (
        extra.get("avaliacao_pagina")
        if isinstance(extra.get("avaliacao_pagina"), (int, float))
        else lot.reference_value
    )
    avaliado = bool(extra.get("avaliado_em") or raw.get("avaliado_em"))
    live = (
        _hydrate_ledger(lot, source, raw, extra, tipo, current_bid, reference_value)
        if avaliado
        else {}
    )
    parecer = extra.get("parecer") if isinstance(extra.get("parecer"), str) else None
    veredito = (
        live.get("veredito")
        if live.get("veredito") in ("nao_aprofundar", "falta_peca", "aprofundar")
        else (raw.get("veredito") if raw.get("veredito") in ("nao_aprofundar", "falta_peca", "aprofundar") else None)
    )
    veredito_titulo = live.get("veredito_titulo") or (raw.get("veredito_titulo") if isinstance(raw.get("veredito_titulo"), str) else None)
    veredito_corpo = live.get("veredito_corpo") or (raw.get("veredito_corpo") if isinstance(raw.get("veredito_corpo"), str) else None)
    if not avaliado:
        veredito = "falta_peca"
        veredito_titulo = "Sem norte"
        veredito_corpo = SEM_NORTE["sem_leitura"]
    if avaliado and live.get("ledger"):
        rebuilt = parecer_from_facts(
            {
                "ledger": live.get("ledger"),
                "veredito_titulo": live.get("veredito_titulo"),
                "veredito_corpo": live.get("veredito_corpo"),
            }
        )
        if rebuilt:
            parecer = rebuilt
    return LotOut(
        id=lot.id,
        auction_id=lot.auction_id,
        external_id=lot.external_id,
        source=source,
        title=lot.title,
        description=lot.description,
        category=lot.category,
        tipo=tipo,
        headline=extra.get("headline"),
        cidade=extra.get("cidade") or cidade_of(lot),
        bairro=extra.get("bairro"),
        endereco=extra.get("endereco") or endereco_of(lot),
        matricula=extra.get("matricula"),
        area=extra.get("area"),
        foto=foto_of(lot) or (extra.get("foto") if isinstance(extra.get("foto"), str) and extra["foto"].startswith("http") and "facebook.com/tr" not in extra["foto"] else None),
        valor_m2_regiao=extra.get("valor_m2_regiao"),
        valor_m2_fonte=extra.get("valor_m2_fonte") if extra.get("valor_m2_fonte") in ("fipezap", "apify") else None,
        valor_m2_n=extra.get("valor_m2_n") if isinstance(extra.get("valor_m2_n"), int) else None,
        apify=extra.get("apify") if extra.get("apify") in ("ok", "poucos", "indisponivel", "sem_token") else None,
        valor_mercado_estimado=extra.get("valor_mercado_estimado"),
        score=live.get("score", raw.get("score")),
        score_tem_comparacao_preco=live.get("score_tem_comparacao_preco", raw.get("score_tem_comparacao_preco")),
        score_motivos=live.get("score_motivos") or raw.get("score_motivos") or [],
        veredito=veredito,
        veredito_titulo=veredito_titulo,
        veredito_corpo=veredito_corpo,
        regime=(
            live.get("regime")
            if live.get("regime") in ("judicial", "extrajudicial", "trabalhista", "indefinido")
            else (raw.get("regime") if raw.get("regime") in ("judicial", "extrajudicial", "trabalhista", "indefinido") else None)
        ),
        cobertura=live.get("cobertura") if live.get("cobertura") is not None else (raw.get("cobertura") if isinstance(raw.get("cobertura"), (int, float)) else None),
        ledger=live.get("ledger") or (raw.get("ledger") if isinstance(raw.get("ledger"), list) else []),
        parecer=parecer,
        ocupacao=_ocupacao_do_ledger(
            live.get("ledger") or (raw.get("ledger") if isinstance(raw.get("ledger"), list) else []),
            extra.get("ocupacao") if extra.get("ocupacao") in ("ocupado", "desocupado") else None,
        ),
        avaliado_em=extra.get("avaliado_em") if isinstance(extra.get("avaliado_em"), str) else None,
        docs=extra.get("docs") if isinstance(extra.get("docs"), list) else [],
        dividas=extra.get("dividas") if isinstance(extra.get("dividas"), dict) else None,
        avaliacao_edital=extra.get("avaliacao_edital") if isinstance(extra.get("avaliacao_edital"), (int, float)) else None,
        avaliacao_fonte=extra.get("avaliacao_fonte") if extra.get("avaliacao_fonte") in ("laudo", "venal_imovel") else None,
        avaliacao_data=extra.get("avaliacao_data") if isinstance(extra.get("avaliacao_data"), str) else None,
        avaliacao_data_origem=extra.get("avaliacao_data_origem") if extra.get("avaliacao_data_origem") in ("laudo", "processo") else None,
        status=extra.get("status") if extra.get("status") in ("aberto", "aguardando", "encerrado") else None,
        processo_cnj=extra.get("processo_cnj") if isinstance(extra.get("processo_cnj"), str) else (raw.get("processo_cnj") if isinstance(raw.get("processo_cnj"), str) else None),
        nao_entrar=True if extra.get("nao_entrar") or raw.get("nao_entrar") else None,
        riscos=extra.get("riscos") if isinstance(extra.get("riscos"), dict) else (raw.get("riscos") if isinstance(raw.get("riscos"), dict) else None),
        infosimples=extra.get("infosimples") if extra.get("infosimples") in ("ok", "nao_encontrado", "indisponivel") else None,
        infosimples_foro=extra.get("infosimples_foro") if isinstance(extra.get("infosimples_foro"), str) else None,
        infosimples_vara=extra.get("infosimples_vara") if isinstance(extra.get("infosimples_vara"), str) else None,
        infosimples_valor_causa=extra.get("infosimples_valor_causa") if isinstance(extra.get("infosimples_valor_causa"), (int, float)) else None,
        infosimples_peticoes_recentes=extra.get("infosimples_peticoes_recentes") if isinstance(extra.get("infosimples_peticoes_recentes"), list) else [],
        trechos=extra.get("trechos") if isinstance(extra.get("trechos"), list) else [],
        pracas=_pracas_out(extra.get("pracas") or raw.get("pracas")),
        minimum_bid=lot.minimum_bid,
        current_bid=(
            extra.get("lance_pagina")
            if isinstance(extra.get("lance_pagina"), (int, float))
            else lot.current_bid
        ),
        reference_value=(
            extra.get("avaliacao_pagina")
            if isinstance(extra.get("avaliacao_pagina"), (int, float))
            else lot.reference_value
        ),
        url=lot.url,
        updated_at=lot.updated_at,
    )
