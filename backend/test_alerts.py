import os

from app.alerts import format_alert_message, should_alert


def test_should_alert_true_above_threshold():
    assert should_alert({"score": 80}, min_score=70) is True


def test_should_alert_false_below_threshold():
    assert should_alert({"score": 50}, min_score=70) is False


def test_should_alert_false_without_score():
    assert should_alert({}, min_score=70) is False


def test_should_alert_false_when_already_alertado():
    assert should_alert({"score": 90, "alertado": True}, min_score=70) is False


def test_should_alert_uses_env_min_score_when_not_passed():
    original = os.environ.get("ALERT_MIN_SCORE")
    os.environ["ALERT_MIN_SCORE"] = "85"
    try:
        assert should_alert({"score": 80}) is False
        assert should_alert({"score": 90}) is True
    finally:
        if original is None:
            os.environ.pop("ALERT_MIN_SCORE", None)
        else:
            os.environ["ALERT_MIN_SCORE"] = original


def test_format_alert_message_includes_score_title_motivos_url():
    msg = format_alert_message(
        title="Casa em Sertãozinho",
        source="zuk",
        score=82,
        motivos=["64% abaixo da avaliação do edital", "sem menção de ocupação/dívida"],
        url="https://example.test/lote/1",
    )
    assert "82" in msg
    assert "Casa em Sertãozinho" in msg
    assert "64% abaixo da avaliação do edital" in msg
    assert "https://example.test/lote/1" in msg


if __name__ == "__main__":
    test_should_alert_true_above_threshold()
    test_should_alert_false_below_threshold()
    test_should_alert_false_without_score()
    test_should_alert_false_when_already_alertado()
    test_should_alert_uses_env_min_score_when_not_passed()
    test_format_alert_message_includes_score_title_motivos_url()
    print("ok")
