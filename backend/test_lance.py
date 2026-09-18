from datetime import datetime
from pathlib import Path
import json

from bs4 import BeautifulSoup

from app.scrapers.lance import _active_praca_price, lots_from_html
from app.scrapers.listing import pracas_from_html, pracas_from_tag
from app.scrapers.registry import source_names

ROOT = Path(__file__).resolve().parent
LANCE = ROOT / "fixtures" / "lance_imoveis.html"


def test_registry_includes_lance():
    assert "lance" in source_names()


def test_lance_listing_is_judicial():
    lots = lots_from_html(LANCE.read_text(encoding="utf-8"), "https://www.grupolance.com.br")
    assert len(lots) >= 1
    lot = lots[0]
    assert lot.external_id == "23514"
    # 1ª praça (R$ 915.043,07) até 17/09/2026 14:13, 2ª (R$ 457.521,54) depois —
    # current_bid depende do horário real de quando o teste roda; o que
    # importa é a consistência: se já é a 2ª praça, reference_value vira a 1ª.
    assert lot.current_bid in (915043.07, 457521.54)
    if lot.current_bid == 457521.54:
        assert lot.reference_value == 915043.07
    else:
        assert lot.reference_value is None
    assert lot.raw_data and ("Guarujá" in lot.raw_data or "Guaruja" in lot.raw_data)
    assert lot.category == "apartamento"
    assert "judicial" in (lot.raw_data or "")
    extra = json.loads(lot.raw_data or "{}")
    pracas = extra.get("pracas") or []
    assert [p["n"] for p in pracas] == [1, 2]
    assert pracas[0]["valor"] == 915043.07
    assert pracas[0]["inicio"].startswith("2026-09-14")
    assert pracas[0]["fim"].startswith("2026-09-17")
    assert pracas[1]["valor"] == 457521.54
    assert pracas[1]["inicio"].startswith("2026-09-17")
    assert lot.url and "23514" in lot.url


def test_active_praca_price_picks_current_phase_by_date():
    """Grupo Lance mostra o preço da 1ª praça em destaque mesmo com a 2ª já
    ativa — _active_praca_price precisa escolher pela data, não pelo
    .card-price. Fixture: 23514 tem 1ª praça até 17/09/2026 14:13 (R$
    915.043,07) e 2ª a partir daí (R$ 457.521,54)."""
    soup = BeautifulSoup(LANCE.read_text(encoding="utf-8"), "html.parser")
    card = soup.select(".card-item")[0]
    assert card.get("data-key") == "23514"

    before = datetime(2026, 9, 15, 12, 0)
    price, avaliacao = _active_praca_price(card, now=before)
    assert price == 915043.07
    assert avaliacao is None

    after = datetime(2026, 9, 18, 12, 0)
    price, avaliacao = _active_praca_price(card, now=after)
    assert price == 457521.54
    assert avaliacao == 915043.07
    pracas = pracas_from_tag(card, now=after)
    assert pracas[0]["valor"] == 915043.07
    assert pracas[1]["valor"] == 457521.54
    assert pracas[1].get("ativa") is True


def test_pracas_pagina_item_tem_encerramento_e_valor():
    html = (ROOT / "fixtures" / "lance_item.html").read_text(encoding="utf-8")
    pracas = pracas_from_html(html)
    assert [p["n"] for p in pracas] == [1, 2]
    assert pracas[0]["valor"] == 7013110.1
    assert pracas[0]["fim"] == "2026-09-17T16:50:00"
    assert pracas[1]["valor"] == 4207866.06
    assert pracas[1]["fim"] == "2026-10-20T16:50:00"
    assert pracas[1].get("ativa") is True


if __name__ == "__main__":
    test_registry_includes_lance()
    test_lance_listing_is_judicial()
    test_active_praca_price_picks_current_phase_by_date()
    test_pracas_pagina_item_tem_encerramento_e_valor()
    print("ok")
