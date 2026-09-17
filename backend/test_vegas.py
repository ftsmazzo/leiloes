from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.scrapers.vegas import (
    VegasScraper,
    cidade_from_vegas,
    parse_br_currency,
    parse_vegas_date,
)

ROOT = Path(__file__).resolve().parent
LISTAGEM = ROOT / "fixtures" / "vegas_listagem.html"
LOTES = ROOT / "fixtures" / "vegas_lotes.html"


def test_parse_helpers():
    assert parse_br_currency("R$1.129.937,72") == 1129937.72
    assert parse_vegas_date("21/09/2026 às 15:00") == datetime(2026, 9, 21, 15, 0)
    assert cidade_from_vegas("Imóveis em Monte Alto/SP") == "Monte Alto"
    assert cidade_from_vegas("Cidade: Jaboticabal/SP") == "Jaboticabal"
    assert cidade_from_vegas("Apartamento 2 dormitorios") is None


def test_listagem_skips_closed_and_simulation():
    html = LISTAGEM.read_text(encoding="utf-8")
    auctions = VegasScraper().auctions_from_html(html)
    assert len(auctions) == 1
    a = auctions[0]
    assert a.external_id == "4257"
    assert a.title == "SICOOB COCRED"
    assert a.starts_at == datetime(2026, 9, 21, 15, 0)
    assert a.url and a.url.endswith("/leilao/4257/lotes")
    assert a.description and "Monte Alto" in a.description


def test_lotes_all_items_in_one_card_body():
    html = LOTES.read_text(encoding="utf-8")
    lots = VegasScraper().lots_from_html(html)
    assert [lot.external_id for lot in lots] == ["9170", "9171"]
    first = lots[0]
    assert first.current_bid == 1129937.72
    assert first.minimum_bid == 1129937.72
    assert first.url and first.url.endswith("/item/9170/detalhes")
    assert first.raw_data and "Monte Alto" in first.raw_data
    assert lots[1].current_bid == 210000
    assert lots[1].raw_data and "Jaboticabal" in lots[1].raw_data


def test_lotes_without_row_do_not_share_first_lot():
    html = """
    <div class="card-body">
      <a href="/item/1/detalhes"><h5>Casa em Sertãozinho/SP</h5><h4 class="mb-0">R$ 10.000,00</h4></a>
      <a href="/item/2/detalhes"><h5>Terreno em Franca/SP</h5><h4 class="mb-0">R$ 20.000,00</h4></a>
    </div>
    """
    lots = VegasScraper().lots_from_html(html)
    assert [lot.external_id for lot in lots] == ["1", "2"]
    assert lots[0].title.startswith("Casa")
    assert lots[0].current_bid == 10000
    assert lots[0].raw_data and "Sertãozinho" in lots[0].raw_data
    assert lots[1].title.startswith("Terreno")
    assert lots[1].current_bid == 20000
    assert lots[1].raw_data and "Franca" in lots[1].raw_data


if __name__ == "__main__":
    test_parse_helpers()
    test_listagem_skips_closed_and_simulation()
    test_lotes_all_items_in_one_card_body()
    test_lotes_without_row_do_not_share_first_lot()
    print("ok")
