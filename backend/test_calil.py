from __future__ import annotations

import json
from pathlib import Path

from app.scrapers.calil import CalilScraper, cidade_from_text
from app.scrapers.registry import source_names

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "fixtures" / "calil_next_data.json"


def test_cidade_from_title():
    assert cidade_from_text("Casa 3 quartos — Sertãozinho/SP") == "Sertãozinho"
    assert cidade_from_text("Casa em Sertaozinho/SP") == "Sertaozinho"
    assert cidade_from_text("Embu-Guaçu/SP") == "Embu-Guaçu"
    assert cidade_from_text("Ribeirão Preto", allow_bare=True) == "Ribeirão Preto"
    assert cidade_from_text("Sertãozinho / SP") == "Sertãozinho"
    assert cidade_from_text("Apartamento 2 dormitorios") is None
    assert cidade_from_text("Apartamento 2 dormitorios", "Ribeirão Preto") is None
    assert (
        cidade_from_text("Apartamento 2 dormitorios")
        or cidade_from_text("Ribeirão Preto", allow_bare=True)
    ) == "Ribeirão Preto"


def test_calil_next_data_fixture():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    html = f'<html><script id="__NEXT_DATA__">{json.dumps(payload)}</script></html>'
    lots = CalilScraper().lots_from_html(html)
    assert len(lots) == 2
    casa = lots[0]
    assert casa.external_id == "818001"
    assert "Sertãozinho" in casa.title
    assert casa.current_bid == 210000
    assert casa.reference_value == 320000
    assert casa.category == "Imóvel"
    assert casa.url and casa.url.endswith("/oferta/casa-sertaozinho-818001")
    assert casa.raw_data and "Sertãozinho" in casa.raw_data
    terreno = lots[1]
    assert terreno.current_bid == 92000


def test_calil_oferta_link_fallback():
    html = """
    <a href="/oferta/galpao-jaboticabal-99">Galpão — Jaboticabal/SP Lance atual: R$ 410.000,00</a>
    """
    lots = CalilScraper().lots_from_html(html)
    assert len(lots) == 1
    assert lots[0].external_id == "99"
    assert lots[0].current_bid == 410000
    assert lots[0].raw_data and "Jaboticabal" in lots[0].raw_data


def test_poisoned_offer_keeps_siblings():
    payload = {
        "props": {
            "pageProps": {
                "data": ["not-a-dict"],
                "offers": {
                    "items": [
                        {
                            "id": "1",
                            "title": "Casa — Sertãozinho/SP",
                            "currentPrice": 100,
                            "friendlyUrl": "casa-1",
                        },
                        {"id": "bad", "title": {"nested": True}, "friendlyUrl": 99},
                        {
                            "id": "3",
                            "title": "Terreno — Ribeirão Preto/SP",
                            "currentPrice": 200,
                            "friendlyUrl": "terreno-3",
                        },
                    ]
                },
            }
        }
    }
    html = f'<html><script id="__NEXT_DATA__">{json.dumps(payload)}</script></html>'
    lots = CalilScraper().lots_from_html(html)
    ids = [lot.external_id for lot in lots]
    assert "1" in ids and "3" in ids
    assert len(lots) >= 2


def test_registry_lists_calil_and_vegas():
    names = source_names()
    assert names == ["calil", "vegas"]


if __name__ == "__main__":
    test_cidade_from_title()
    test_calil_next_data_fixture()
    test_calil_oferta_link_fallback()
    test_poisoned_offer_keeps_siblings()
    test_registry_lists_calil_and_vegas()
    print("ok")
