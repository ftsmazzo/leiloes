"""
OCR de PDF escaneado via OpenRouter (visão). Só quando pypdf não tira texto.

Sem chave, devolve vazio — testes e CI não batem na API.
"""
from __future__ import annotations

import base64
import os
from io import BytesIO
from typing import Callable, Optional

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_PAGES = 2
MAX_SIDE = 1280
OCR_TIMEOUT = 60.0


def pages_to_jpegs(data: bytes, max_pages: int = MAX_PAGES) -> list[bytes]:
    if not data:
        return []
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return []
    try:
        pdf = pdfium.PdfDocument(data)
    except Exception:
        return []
    out: list[bytes] = []
    try:
        n = min(len(pdf), max_pages)
        for i in range(n):
            page = pdf[i]
            bitmap = page.render(scale=1.4)
            image = bitmap.to_pil()
            image.thumbnail((MAX_SIDE, MAX_SIDE))
            if image.mode != "RGB":
                image = image.convert("RGB")
            buf = BytesIO()
            image.save(buf, format="JPEG", quality=70)
            out.append(buf.getvalue())
    except Exception:
        return []
    return out


def ocr_pdf(data: bytes, fetch: Optional[Callable] = None) -> str:
    """Transcreve páginas de PDF escaneado. Não inventa se a API falhar."""
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if fetch is None and not key:
        return ""
    images = pages_to_jpegs(data)
    if not images:
        return ""
    model = (
        os.getenv("OPENROUTER_OCR_MODEL")
        or os.getenv("OPENROUTER_EXTRACT_MODEL")
        or "google/gemini-2.0-flash-001"
    ).strip()
    content: list[dict] = [
        {
            "type": "text",
            "text": (
                "Transcreva o texto visível nestas páginas de edital, matrícula ou laudo. "
                "Só o que está escrito. Português. Não invente cláusula, valor nem ocupação."
            ),
        }
    ]
    for jpeg in images:
        b64 = base64.b64encode(jpeg).decode("ascii")
        content.append(
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
        )
    post = fetch or httpx.post
    try:
        r = post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {key or 'test'}",
                "Content-Type": "application/json",
                "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL") or "http://127.0.0.1:8050",
                "X-Title": os.getenv("OPENROUTER_APP_NAME") or "leiloes",
            },
            json={
                "model": model,
                "temperature": 0,
                "messages": [{"role": "user", "content": content}],
            },
            timeout=OCR_TIMEOUT,
        )
        if getattr(r, "status_code", 500) >= 400:
            return ""
        payload = r.json() if callable(getattr(r, "json", None)) else {}
        text = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
    except Exception:
        return ""
    text = str(text).strip()
    return text[:14000]
