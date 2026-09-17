"""
Envio de alerta via Telegram. TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID no
.env — sem eles, o envio é pulado silenciosamente. Alerta é best-effort:
uma falha aqui nunca pode derrubar o scrape.
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def telegram_configured() -> bool:
    return bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip() and os.getenv("TELEGRAM_CHAT_ID", "").strip())


def send_telegram_alert(text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False
    try:
        r = httpx.post(
            TELEGRAM_API_URL.format(token=token),
            json={"chat_id": chat_id, "text": text},
            timeout=10.0,
        )
        return r.status_code == 200
    except Exception:
        return False
