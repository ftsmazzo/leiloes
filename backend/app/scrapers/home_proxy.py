"""
Cliente do scrape-proxy na casa (WireGuard / Tailscale Funnel).
Só Calil e Vegas usam isto — o resto segue direto do VPS.
"""
from __future__ import annotations

import os
from typing import Optional
from urllib.parse import urlparse

import httpx

ALLOWED_HOSTS = frozenset(
    {
        "www.calilleiloes.com.br",
        "calilleiloes.com.br",
        "www.vegasleiloes.com.br",
        "vegasleiloes.com.br",
    }
)


def configured() -> bool:
    return bool((os.getenv("SCRAPE_PROXY_URL") or "").strip())


def _base() -> str:
    return (os.getenv("SCRAPE_PROXY_URL") or "").strip().rstrip("/")


def _token() -> str:
    return (os.getenv("SCRAPE_PROXY_TOKEN") or "").strip()


def allowed_url(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return False
    return host.lower() in ALLOWED_HOSTS


class HomeProxyError(RuntimeError):
    pass


async def fetch_text(url: str, *, timeout: float = 45.0) -> str:
    """GET via proxy da casa. Levanta HomeProxyError se falhar."""
    if not configured():
        raise HomeProxyError("SCRAPE_PROXY_URL não configurado")
    if not allowed_url(url):
        raise HomeProxyError(f"URL fora da allowlist: {url}")
    token = _token()
    if not token:
        raise HomeProxyError("SCRAPE_PROXY_TOKEN vazio")
    endpoint = f"{_base()}/fetch"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        try:
            r = await client.post(endpoint, headers=headers, json={"url": url})
        except httpx.HTTPError as exc:
            raise HomeProxyError(f"proxy casa inacessível: {exc}") from exc
    if r.status_code == 401:
        raise HomeProxyError("proxy casa: TOKEN inválido")
    if r.status_code >= 400:
        raise HomeProxyError(f"proxy casa HTTP {r.status_code}: {r.text[:200]}")
    try:
        data = r.json()
    except Exception as exc:
        raise HomeProxyError("proxy casa: JSON inválido") from exc
    status = int(data.get("status") or 0)
    text = data.get("text")
    if not isinstance(text, str):
        raise HomeProxyError("proxy casa: sem text")
    if status >= 400:
        raise HomeProxyError(f"origem HTTP {status} via proxy para {url}")
    return text


async def get_html(client: httpx.AsyncClient, url: str, *, via_home: Optional[bool] = None) -> str:
    """GET HTML: pela casa se SCRAPE_PROXY_URL estiver setado (ou via_home=True)."""
    use = configured() if via_home is None else via_home
    if use:
        return await fetch_text(url)
    r = await client.get(url)
    r.raise_for_status()
    return r.text
