import asyncio
import os

from app.scrapers import home_proxy


def test_allowed_url():
    assert home_proxy.allowed_url("https://www.calilleiloes.com.br/lotes/imovel")
    assert home_proxy.allowed_url("https://www.vegasleiloes.com.br/leiloes")
    assert not home_proxy.allowed_url("https://www.zukleiloes.com.br/x")
    assert not home_proxy.allowed_url("https://evil.example/calilleiloes.com.br")


def test_configured_depends_on_env():
    had = os.environ.pop("SCRAPE_PROXY_URL", None)
    try:
        assert home_proxy.configured() is False
        os.environ["SCRAPE_PROXY_URL"] = "https://proxy.example"
        assert home_proxy.configured() is True
    finally:
        if had is None:
            os.environ.pop("SCRAPE_PROXY_URL", None)
        else:
            os.environ["SCRAPE_PROXY_URL"] = had


def test_fetch_text_usa_proxy():
    os.environ["SCRAPE_PROXY_URL"] = "https://proxy.example"
    os.environ["SCRAPE_PROXY_TOKEN"] = "segredo"

    class FakeResp:
        status_code = 200

        def json(self):
            return {"status": 200, "url": "https://www.calilleiloes.com.br/x", "text": "<html>ok</html>"}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            assert url.endswith("/fetch")
            assert headers["Authorization"] == "Bearer segredo"
            assert "calilleiloes" in json["url"]
            return FakeResp()

    original = home_proxy.httpx.AsyncClient
    home_proxy.httpx.AsyncClient = FakeClient
    try:
        text = asyncio.run(home_proxy.fetch_text("https://www.calilleiloes.com.br/lotes/imovel"))
        assert text == "<html>ok</html>"
    finally:
        home_proxy.httpx.AsyncClient = original
        os.environ.pop("SCRAPE_PROXY_URL", None)
        os.environ.pop("SCRAPE_PROXY_TOKEN", None)


def test_fetch_text_rejeita_host_estranho():
    os.environ["SCRAPE_PROXY_URL"] = "https://proxy.example"
    os.environ["SCRAPE_PROXY_TOKEN"] = "segredo"
    try:
        try:
            asyncio.run(home_proxy.fetch_text("https://evil.example/"))
            assert False, "deveria falhar"
        except home_proxy.HomeProxyError as exc:
            assert "allowlist" in str(exc)
    finally:
        os.environ.pop("SCRAPE_PROXY_URL", None)
        os.environ.pop("SCRAPE_PROXY_TOKEN", None)


if __name__ == "__main__":
    test_allowed_url()
    test_configured_depends_on_env()
    test_fetch_text_usa_proxy()
    test_fetch_text_rejeita_host_estranho()
    print("ok")
