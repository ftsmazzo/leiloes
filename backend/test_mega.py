from pathlib import Path

from app.scrapers.mega import lots_from_html
from app.scrapers.registry import source_names

ROOT = Path(__file__).resolve().parent
MEGA = ROOT / "fixtures" / "mega_imoveis.html"


def test_registry_includes_mega():
    assert "mega" in source_names()


def test_mega_skips_auction_cards():
    lots = lots_from_html(MEGA.read_text(encoding="utf-8"), "https://www.megaleiloes.com.br")
    ids = [lot.external_id for lot in lots]
    assert "X128475" in ids
    assert all(not x.startswith("ML") for x in ids)
    formiga = next(lot for lot in lots if lot.external_id == "X128475")
    assert formiga.current_bid == 2300000
    assert formiga.raw_data and "Formiga" in formiga.raw_data
    assert "extrajudicial" in (formiga.raw_data or "")


if __name__ == "__main__":
    test_registry_includes_mega()
    test_mega_skips_auction_cards()
    print("ok")
