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
    assert source_names() == ["calil", "vegas", "zuk", "mega", "lance"]


def test_lot_to_out_exposes_market_reference_when_present():
    lot = SimpleNamespace(
        id=2,
        auction_id=9,
        external_id="818002",
        title="Apartamento na cidade de São Paulo/SP",
        description=None,
        category="Imóvel",
        minimum_bid=200000,
        current_bid=200000,
        reference_value=None,
        url=None,
        raw_data='{"cidade": "São Paulo", "area": "50 m²", "valor_m2_regiao": 12055.0, "valor_mercado_estimado": 602750.0}',
        updated_at=datetime(2026, 9, 17),
    )
    out = lot_to_out(lot, "calil")
    assert out.valor_m2_regiao == 12055.0
    assert out.valor_mercado_estimado == 602750.0


def test_lot_to_out_market_reference_absent_is_none_not_zero():
    lot = SimpleNamespace(
        id=3,
        auction_id=9,
        external_id="818003",
        title="Casa em Formiga",
        description=None,
        category="Imóvel",
        minimum_bid=100000,
        current_bid=100000,
        reference_value=None,
        url=None,
        raw_data='{"cidade": "Formiga"}',
        updated_at=datetime(2026, 9, 17),
    )
    out = lot_to_out(lot, "mega")
    assert out.valor_m2_regiao is None
    assert out.valor_mercado_estimado is None


if __name__ == "__main__":
    test_lot_to_out_exposes_source_and_cidade()
    test_registry_sources_are_catalog_tabs()
    test_lot_to_out_exposes_market_reference_when_present()
    test_lot_to_out_market_reference_absent_is_none_not_zero()
    print("ok")
