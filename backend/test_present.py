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


def test_lot_to_out_exposes_score_when_present():
    lot = SimpleNamespace(
        id=4,
        auction_id=9,
        external_id="818004",
        title="Casa em 2ª Praça",
        description=None,
        category="Imóvel",
        minimum_bid=100000,
        current_bid=100000,
        reference_value=None,
        url=None,
        raw_data='{"score": 62, "score_tem_comparacao_preco": false, "score_motivos": ["sem referência de preço pra comparar — score calculado só com risco/praça", "já na 2ª praça — desconto judicial maior, mas prazo mais curto"]}',
        updated_at=datetime(2026, 9, 17),
    )
    out = lot_to_out(lot, "lance")
    assert out.score == 62
    assert out.score_tem_comparacao_preco is False
    assert len(out.score_motivos) == 2


def test_lot_to_out_score_absent_defaults_to_empty_motivos():
    lot = SimpleNamespace(
        id=5,
        auction_id=9,
        external_id="818005",
        title="Casa antiga no banco",
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
    assert out.score is None
    assert out.score_motivos == []


def test_lot_to_out_exposes_riscos_juridicos():
    lot = SimpleNamespace(
        id=6,
        auction_id=9,
        external_id="818006",
        title="Casa judicial",
        description=None,
        category="Imóvel",
        minimum_bid=100000,
        current_bid=100000,
        reference_value=None,
        url=None,
        raw_data='{"processo_cnj": "0001234-11.2012.8.26.0100", "nao_entrar": true, "riscos": {"citacao": "nao_citado", "nao_entrar": true}}',
        updated_at=datetime(2026, 9, 17),
    )
    out = lot_to_out(lot, "calil")
    assert out.processo_cnj == "0001234-11.2012.8.26.0100"
    assert out.nao_entrar is True
    assert out.riscos["citacao"] == "nao_citado"


def test_lot_to_out_usa_preco_da_pagina():
    lot = SimpleNamespace(
        id=7,
        auction_id=9,
        external_id="28639",
        title="Terreno Porto Ferreira",
        description=None,
        category="Terreno",
        minimum_bid=7013110.10,
        current_bid=7013110.10,
        reference_value=7013110.10,
        url=None,
        raw_data='{"lance_pagina": 4207866.06, "avaliacao_pagina": 7013110.1}',
        updated_at=datetime(2026, 9, 17),
    )
    out = lot_to_out(lot, "lance")
    assert out.current_bid == 4207866.06
    assert out.reference_value == 7013110.1


def test_lot_to_out_exposes_pracas():
    lot = SimpleNamespace(
        id=8,
        auction_id=9,
        external_id="28639",
        title="Terreno Porto Ferreira",
        description=None,
        category="Terreno",
        minimum_bid=4207866.06,
        current_bid=4207866.06,
        reference_value=7013110.10,
        url=None,
        raw_data='{"pracas": [{"n": 1, "fim": "2026-09-17T16:50:00", "valor": 7013110.1}, {"n": 2, "fim": "2026-10-20T16:50:00", "valor": 4207866.06, "ativa": true}]}',
        updated_at=datetime(2026, 9, 17),
    )
    out = lot_to_out(lot, "lance")
    assert out.pracas[0]["n"] == 1
    assert out.pracas[0]["valor"] == 7013110.1
    assert out.pracas[1]["ativa"] is True


if __name__ == "__main__":
    test_lot_to_out_exposes_source_and_cidade()
    test_registry_sources_are_catalog_tabs()
    test_lot_to_out_exposes_market_reference_when_present()
    test_lot_to_out_market_reference_absent_is_none_not_zero()
    test_lot_to_out_exposes_score_when_present()
    test_lot_to_out_score_absent_defaults_to_empty_motivos()
    test_lot_to_out_exposes_riscos_juridicos()
    test_lot_to_out_usa_preco_da_pagina()
    test_lot_to_out_exposes_pracas()
    print("ok")
