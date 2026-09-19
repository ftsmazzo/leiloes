"""Monta DTOs da API a partir dos modelos persistidos."""
from __future__ import annotations

from app.api.schemas import LotOut
from app.models.schemas import LotModel
from app.search import cidade_of, endereco_of, foto_of, raw_dict, tipo_of
from app.scrapers.extract import format_card, tipo_from_text


def lot_to_out(lot: LotModel, source: str) -> LotOut:
    raw = raw_dict(lot)
    extra = format_card(
        getattr(lot, "title", None) or "",
        getattr(lot, "description", None),
        raw,
    )
    tipo = extra.get("tipo") or tipo_of(lot) or tipo_from_text(getattr(lot, "title", None), getattr(lot, "category", None))
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
        valor_mercado_estimado=extra.get("valor_mercado_estimado"),
        score=raw.get("score"),
        score_tem_comparacao_preco=raw.get("score_tem_comparacao_preco"),
        score_motivos=raw.get("score_motivos") or [],
        parecer=extra.get("parecer") if isinstance(extra.get("parecer"), str) else None,
        ocupacao=extra.get("ocupacao") if extra.get("ocupacao") in ("ocupado", "desocupado") else None,
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
