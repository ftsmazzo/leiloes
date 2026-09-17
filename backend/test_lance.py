from pathlib import Path

from app.scrapers.lance import lots_from_html
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
    assert lot.current_bid == 915043.07
    assert lot.raw_data and ("Guarujá" in lot.raw_data or "Guaruja" in lot.raw_data)
    assert lot.category == "apartamento"
    assert "judicial" in (lot.raw_data or "")
    assert lot.url and "23514" in lot.url


if __name__ == "__main__":
    test_registry_includes_lance()
    test_lance_listing_is_judicial()
    print("ok")
