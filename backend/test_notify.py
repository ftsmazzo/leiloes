import os

import app.notify as notify


def _clear_telegram_env():
    for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        os.environ.pop(key, None)


def test_telegram_not_configured_without_env():
    original = {k: os.environ.get(k) for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")}
    _clear_telegram_env()
    try:
        assert notify.telegram_configured() is False
        assert notify.send_telegram_alert("oi") is False
    finally:
        for k, v in original.items():
            if v is not None:
                os.environ[k] = v


def test_telegram_configured_with_both_env_vars():
    original = {k: os.environ.get(k) for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")}
    os.environ["TELEGRAM_BOT_TOKEN"] = "123:abc"
    os.environ["TELEGRAM_CHAT_ID"] = "999"
    try:
        assert notify.telegram_configured() is True
    finally:
        for k, v in original.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_send_telegram_alert_returns_true_on_200(monkeypatch):
    os.environ["TELEGRAM_BOT_TOKEN"] = "123:abc"
    os.environ["TELEGRAM_CHAT_ID"] = "999"

    class FakeResponse:
        status_code = 200

    def fake_post(url, json=None, timeout=None):
        assert "123:abc" in url
        assert json["chat_id"] == "999"
        return FakeResponse()

    monkeypatch.setattr(notify.httpx, "post", fake_post)
    assert notify.send_telegram_alert("oportunidade!") is True


def test_send_telegram_alert_returns_false_on_error_status(monkeypatch):
    os.environ["TELEGRAM_BOT_TOKEN"] = "123:abc"
    os.environ["TELEGRAM_CHAT_ID"] = "999"

    class FakeResponse:
        status_code = 400

    monkeypatch.setattr(notify.httpx, "post", lambda *a, **k: FakeResponse())
    assert notify.send_telegram_alert("oportunidade!") is False


def test_send_telegram_alert_returns_false_on_exception(monkeypatch):
    os.environ["TELEGRAM_BOT_TOKEN"] = "123:abc"
    os.environ["TELEGRAM_CHAT_ID"] = "999"

    def raise_error(*a, **k):
        raise RuntimeError("rede fora")

    monkeypatch.setattr(notify.httpx, "post", raise_error)
    assert notify.send_telegram_alert("oportunidade!") is False


if __name__ == "__main__":
    class _FakeMonkeypatch:
        def setattr(self, obj, name, value):
            setattr(obj, name, value)

    mp = _FakeMonkeypatch()
    test_telegram_not_configured_without_env()
    test_telegram_configured_with_both_env_vars()
    test_send_telegram_alert_returns_true_on_200(mp)
    test_send_telegram_alert_returns_false_on_error_status(mp)
    test_send_telegram_alert_returns_false_on_exception(mp)
    print("ok")
