from __future__ import annotations

from types import SimpleNamespace

from app.search import filter_lots, lot_matches


def _lot(**kwargs):
    defaults = dict(
        title="Casa 3 quartos — Sertãozinho/SP",
        description=None,
        category="Imóvel",
        current_bid=150000,
        minimum_bid=150000,
        raw_data='{"cidade": "Sertãozinho", "tipo": "casa"}',
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_cidade_accent_and_raw_data():
    lot = _lot()
    assert lot_matches(lot, cidade="Sertaozinho")
    assert lot_matches(lot, cidade="sertãozinho")
    assert not lot_matches(lot, cidade="Franca")
    assert not lot_matches(lot, cidade="rio")


def test_cidade_ignores_description_and_uses_title_fallback():
    noisy = _lot(description="Referência em Franca e terreno comercial")
    assert not lot_matches(noisy, cidade="Franca")
    assert not lot_matches(noisy, tipo="terreno")
    fallback = _lot(raw_data=None, title="Casa em Jaboticabal/SP")
    assert lot_matches(fallback, cidade="Jaboticabal")


def test_tipo_and_teto():
    lot = _lot()
    assert lot_matches(lot, tipo="casa")
    assert lot_matches(lot, tipo="imovel")
    assert lot_matches(lot, teto=200000)
    assert not lot_matches(lot, teto=100000)
    assert not lot_matches(lot, tipo="terreno")


def test_teto_skips_lot_without_bid():
    lot = _lot(current_bid=None, minimum_bid=None)
    assert not lot_matches(lot, teto=200000)
    assert lot_matches(lot)


def test_tipo_imovel_matches_casa_and_apartamento():
    casa = _lot()
    apto = _lot(title="Apartamento 2 dormitórios — Ribeirão Preto/SP", category="Apartamento", raw_data='{"cidade": "Ribeirão Preto", "tipo": "apartamento"}')
    assert lot_matches(casa, tipo="imovel")
    assert lot_matches(apto, tipo="imovel")
    assert lot_matches(apto, tipo="apartamento")
    assert not lot_matches(casa, tipo="terreno")


def test_q_matches_endereco():
    lot = _lot(raw_data='{"cidade": "Sertãozinho", "endereco": "Rua das Flores, 100"}')
    assert lot_matches(lot, q="flores")
    assert not lot_matches(lot, q="Jaboticabal")


def test_tipo_ignores_title_dump():
    honda = _lot(title="Honda CG 160", category=None, raw_data="{}")
    assert lot_matches(honda, tipo="veiculo")
    assert not lot_matches(honda, tipo="casa")
    fronhas = _lot(title="3.400 Fronhas marca Capri", category="Diversos", raw_data="{}")
    assert not lot_matches(fronhas, tipo="sala")
    assert not lot_matches(fronhas, tipo="imovel")


def test_filter_lots_combines_criteria():
    lots = [
        _lot(title="Casa em Sertãozinho/SP", raw_data='{"cidade": "Sertãozinho"}', current_bid=150000),
        _lot(title="Terreno em Franca/SP", category="Terreno", raw_data='{"cidade": "Franca"}', current_bid=90000),
        _lot(title="Casa em Franca/SP", raw_data='{"cidade": "Franca"}', current_bid=300000),
    ]
    found = filter_lots(lots, cidade="Franca", tipo="casa", teto=250000)
    assert len(found) == 0
    found = filter_lots(lots, cidade="Franca", tipo="casa", teto=400000)
    assert len(found) == 1
    assert "Franca" in found[0].title
    found = filter_lots(lots, cidade="Sertaozinho", tipo="casa", teto=200000)
    assert len(found) == 1


if __name__ == "__main__":
    test_cidade_accent_and_raw_data()
    test_cidade_ignores_description_and_uses_title_fallback()
    test_tipo_and_teto()
    test_teto_skips_lot_without_bid()
    test_tipo_imovel_matches_casa_and_apartamento()
    test_q_matches_endereco()
    test_tipo_ignores_title_dump()
    test_filter_lots_combines_criteria()
    print("ok")
