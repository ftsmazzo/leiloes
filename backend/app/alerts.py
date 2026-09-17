"""
Decide quando avisar sobre uma oportunidade e monta a mensagem.

Não duplica: só considera lote cujo raw_data ainda não tem "alertado": true
(esse flag é preservado entre re-scrapes por persist.py, que senão
sobrescreveria raw_data inteiro a cada rodada e reenviaria o alerta sempre).
"""
from __future__ import annotations

import os
from typing import Any, Optional

DEFAULT_MIN_SCORE = 70


def alert_min_score() -> int:
    raw = os.getenv("ALERT_MIN_SCORE", "").strip()
    try:
        return int(raw) if raw else DEFAULT_MIN_SCORE
    except ValueError:
        return DEFAULT_MIN_SCORE


def should_alert(extra: dict[str, Any], min_score: Optional[int] = None) -> bool:
    if extra.get("alertado"):
        return False
    score = extra.get("score")
    if not isinstance(score, int):
        return False
    threshold = alert_min_score() if min_score is None else min_score
    return score >= threshold


def alert_status() -> dict[str, Any]:
    from app.notify import telegram_configured

    return {"telegram": telegram_configured(), "min_score": alert_min_score()}


def format_alert_message(
    *,
    title: str,
    source: str,
    score: int,
    motivos: list[str],
    url: Optional[str],
) -> str:
    linhas = [f"Oportunidade (score {score}) - {source}", title]
    for motivo in motivos[:3]:
        linhas.append(f"- {motivo}")
    if url:
        linhas.append(url)
    return "\n".join(linhas)
