from datetime import datetime
from types import SimpleNamespace

from app.api.present import lot_to_out
from app.scrapers.registry import source_names


def test_lot_to_out_exposes_source_and_cidade():
    lot = SimpleNamespace(
        id=1,
        auction_id=9,
        external_id="818001",
        title="Casa 3 quartos",
        description=None,
        category="Imóvel",
        minimum_bid=150000,
        current_bid=150000,
        reference_value=320000,
        url="https://example.test/oferta/818001",
        raw_data='{"cidade": "Sertãozinho"}',
        updated_at=datetime(2026, 9, 17),
    )
    out = lot_to_out(lot, "calil")
    assert out.source == "calil"
    assert out.cidade == "Sertãozinho"
    assert out.auction_id == 9
    assert out.current_bid == 150000


def test_registry_sources_are_catalog_tabs():
    assert source_names() == ["calil", "vegas", "zuk", "mega"]


if __name__ == "__main__":
    test_lot_to_out_exposes_source_and_cidade()
    test_registry_sources_are_catalog_tabs()
    print("ok")
