import os
from types import SimpleNamespace
from unittest.mock import patch

from app.ocr import ocr_pdf


def test_ocr_sem_chave_nao_chama_rede():
    env = {k: v for k, v in os.environ.items() if k != "OPENROUTER_API_KEY"}
    with patch.dict(os.environ, env, clear=True):
        with patch("app.ocr.pages_to_jpegs") as boom:
            boom.side_effect = AssertionError("não deveria renderizar")
            assert ocr_pdf(b"%PDF") == ""


def test_ocr_usa_texto_do_modelo():
    fake = SimpleNamespace(
        status_code=200,
        json=lambda: {
            "choices": [
                {"message": {"content": "Matrícula 12.345. Usufruto vitalício em favor de Maria."}}
            ]
        },
    )
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "x"}):
        with patch("app.ocr.pages_to_jpegs", return_value=[b"fakejpeg"]):
            with patch("app.ocr.httpx.post", return_value=fake):
                text = ocr_pdf(b"%PDF")
    assert "Usufruto" in text
    assert "12.345" in text


if __name__ == "__main__":
    test_ocr_sem_chave_nao_chama_rede()
    test_ocr_usa_texto_do_modelo()
    print("ok")
