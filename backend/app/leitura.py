"""Contagem da leitura nos últimos 7 dias. Sem analytics novo."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional


def resumir_leitura(
    raws: list[Optional[str]],
    *,
    agora: Optional[datetime] = None,
    dias: int = 7,
) -> dict[str, int]:
    momento = agora or datetime.now(timezone.utc)
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    limite = momento - timedelta(days=dias)
    com_peca = sem_peca = ocr_vazio = 0
    for blob in raws:
        raw = _json(blob)
        if not raw:
            continue
        quando = _quando(raw.get("avaliado_em"))
        if quando is None or quando < limite or quando > momento:
            continue
        if raw.get("docs_limitados"):
            sem_peca += 1
        else:
            com_peca += 1
        if _ocr_vazio(raw):
            ocr_vazio += 1
    return {
        "dias": dias,
        "com_peca": com_peca,
        "sem_peca": sem_peca,
        "ocr_vazio": ocr_vazio,
    }


def _json(blob: Optional[str]) -> dict[str, Any]:
    if not blob:
        return {}
    try:
        parsed = json.loads(blob)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _quando(stamp: Any) -> Optional[datetime]:
    if not isinstance(stamp, str) or len(stamp) < 10:
        return None
    try:
        dt = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _ocr_vazio(raw: dict[str, Any]) -> bool:
    if raw.get("edital_sem_texto"):
        return True
    docs = raw.get("docs")
    if not isinstance(docs, list):
        return False
    for doc in docs:
        if not isinstance(doc, dict) or not doc.get("scanned"):
            continue
        if doc.get("ocr_curto"):
            continue
        if int(doc.get("chars") or 0) == 0:
            return True
    return False
