"""
Executa todos os scrapers e persiste no banco.
Uso: python -m app.scrapers.run_all
Ou: POST /api/run-scrape (pela API).
"""
import asyncio
import os
import sys

# Garantir que o app está no path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.models.database import Base, engine, AsyncSessionLocal
from app.scrapers.persist import persist_auctions
from app.scrapers.registry import all_scrapers
from app.scrapers.extract import enrich_extra, extra_json
from app.scrapers.market_price import estimate_market_value
from app.scoring import compute_score
from app.alerts import should_alert, format_alert_message
from app.notify import send_telegram_alert, telegram_configured
import json


def _process_alerts(touched) -> int:
    """Manda alerta pros lotes recem-persistidos que passam do score minimo
    e ainda nao foram avisados. Best-effort: falha de envio nao propaga."""
    if not telegram_configured():
        return 0
    sent = 0
    for lot, source in touched:
        extra = {}
        if lot.raw_data:
            try:
                parsed = json.loads(lot.raw_data)
                if isinstance(parsed, dict):
                    extra = parsed
            except json.JSONDecodeError:
                extra = {}
        if not should_alert(extra):
            continue
        message = format_alert_message(
            title=lot.title,
            source=source,
            score=extra.get("score"),
            motivos=extra.get("score_motivos") or [],
            url=lot.url,
        )
        if send_telegram_alert(message):
            extra["alertado"] = True
            lot.raw_data = extra_json(extra)
            sent += 1
    return sent


def _enrich_auctions(auctions, cap: int = 12) -> None:
    used = 0
    for auction in auctions:
        for lot in auction.lots:
            extra = {}
            if lot.raw_data:
                try:
                    parsed = json.loads(lot.raw_data)
                    if isinstance(parsed, dict):
                        extra = parsed
                except json.JSONDecodeError:
                    extra = {}
            filled = enrich_extra(lot.title, lot.description, extra, use_ai=used < cap)
            if filled.get("extract") in ("gliner", "mistral"):
                used += 1
            mercado = estimate_market_value(filled.get("cidade"), filled.get("area"))
            if mercado:
                filled.update(mercado)
            score_info = compute_score(
                title=lot.title,
                description=lot.description,
                current_bid=lot.current_bid,
                minimum_bid=lot.minimum_bid,
                reference_value=lot.reference_value,
                valor_mercado_estimado=filled.get("valor_mercado_estimado"),
                riscos=filled.get("riscos") if isinstance(filled.get("riscos"), dict) else None,
            )
            filled["score"] = score_info["score"]
            filled["score_tem_comparacao_preco"] = score_info["tem_comparacao_preco"]
            filled["score_motivos"] = score_info["motivos"]
            lot.raw_data = extra_json(filled)
            if filled.get("tipo") and not lot.category:
                lot.category = str(filled["tipo"])


async def run_all(on_progress=None):
    """Retorna dict com total_auctions, total_lots, by_source e errors.

    on_progress(source_name, summary_parcial), se passado, e chamado apos cada
    scraper terminar (ok ou com erro) — usado pra reportar progresso numa
    rodada assincrona (ver POST /api/run-scrape).
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    scrapers = all_scrapers()
    summary = {"total_auctions": 0, "total_lots": 0, "by_source": {}, "errors": [], "alertas_enviados": 0}

    async with AsyncSessionLocal() as session:
        for scraper in scrapers:
            try:
                print(f"Executando scraper: {scraper.source_name}...")
                auctions = await scraper.scrape()
                n_auctions, n_lots = len(auctions), sum(len(a.lots) for a in auctions)
                print(f"  -> {n_auctions} leilão(ões), {n_lots} lote(s)")
                _enrich_auctions(auctions)
                summary["by_source"][scraper.source_name] = {"auctions": n_auctions, "lots": n_lots}
                summary["total_auctions"] += n_auctions
                summary["total_lots"] += n_lots
                touched = await session.run_sync(persist_auctions, auctions)
                summary["alertas_enviados"] += _process_alerts(touched)
                await session.commit()
            except Exception as e:
                await session.rollback()
                print(f"Erro no scraper {scraper.source_name}: {e}")
                summary["errors"].append({"source": scraper.source_name, "error": str(e)})
            if on_progress is not None:
                on_progress(scraper.source_name, summary)
            await asyncio.sleep(1)  # Respeito entre fontes
    print("Scrapers concluídos.")
    return summary


if __name__ == "__main__":
    asyncio.run(run_all())
