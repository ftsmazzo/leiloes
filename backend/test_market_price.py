from app.scrapers.extract import area_from_text
from app.scrapers.market_price import (
    PRICE_PER_M2_BY_CIDADE,
    _area_m2,
    estimate_market_value,
    price_per_m2,
)


def test_tabela_tem_56_cidades_do_informe():
    cidades = {k for k in PRICE_PER_M2_BY_CIDADE if k != "distrito federal"}
    assert len(cidades) == 56
    assert PRICE_PER_M2_BY_CIDADE["brasilia"] == PRICE_PER_M2_BY_CIDADE["distrito federal"]


def test_price_per_m2_known_city_case_and_accent_insensitive():
    assert price_per_m2("São Paulo") == 12143.0
    assert price_per_m2("sao paulo") == 12143.0
    assert price_per_m2("SÃO PAULO") == 12143.0
    assert price_per_m2("Ribeirão Preto") == 5344.0
    assert price_per_m2("Guarujá") == 7035.0
    assert price_per_m2("Brasília") == 10369.0
    assert price_per_m2("Distrito Federal") == 10369.0


def test_price_per_m2_unknown_city_returns_none():
    assert price_per_m2("Formiga") is None
    assert price_per_m2("Brodowski") is None
    assert price_per_m2(None) is None
    assert price_per_m2("") is None


def test_estimate_market_value_known_city_and_area():
    result = estimate_market_value("São Paulo", "200 m²")
    assert result["valor_m2_regiao"] == 12143.0
    assert result["valor_mercado_estimado"] == 2428600.0
    assert result["valor_m2_fonte"] == "fipezap"
    assert result["valor_m2_mes"] == "2026-08"


def test_estimate_market_value_missing_city_or_area_returns_none():
    assert estimate_market_value(None, "200 m²") is None
    assert estimate_market_value("São Paulo", None) is None
    assert estimate_market_value("Formiga", "200 m²") is None
    assert estimate_market_value("São Paulo", "não numérico") is None


def test_estimate_market_value_nao_aplica_fipezap_em_terreno():
    assert estimate_market_value("São Paulo", "200 m²", tipo="terreno") is None
    assert estimate_market_value("Ribeirão Preto", 85.0, tipo="apartamento") == {
        "valor_m2_regiao": 5344.0,
        "valor_mercado_estimado": 454240.0,
        "valor_m2_fonte": "fipezap",
        "valor_m2_mes": "2026-08",
    }


def test_area_br_com_mais_de_duas_casas_nao_vira_milhar():
    """Vegas: «área total de 76,7508 m²» não pode virar 7508 m²."""
    assert area_from_text("área total de 76,7508 m², sendo 66,1738 m²") == "76,7508 m²"
    assert _area_m2("76,7508 m²") == 76.7508
    assert _area_m2("1.234,56 m²") == 1234.56
    mkt = estimate_market_value("Ribeirão Preto", "76,7508 m²", tipo="apartamento")
    assert mkt is not None
    assert mkt["valor_mercado_estimado"] == round(5344.0 * 76.7508, 2)


def test_estimate_recusa_area_absurda_em_apartamento():
    assert estimate_market_value("Ribeirão Preto", "6908 m²", tipo="apartamento") is None
    assert estimate_market_value("Ribeirão Preto", "4200 m²", tipo="apartamento") is None


if __name__ == "__main__":
    test_tabela_tem_56_cidades_do_informe()
    test_price_per_m2_known_city_case_and_accent_insensitive()
    test_price_per_m2_unknown_city_returns_none()
    test_estimate_market_value_known_city_and_area()
    test_estimate_market_value_missing_city_or_area_returns_none()
    test_estimate_market_value_nao_aplica_fipezap_em_terreno()
    test_area_br_com_mais_de_duas_casas_nao_vira_milhar()
    test_estimate_recusa_area_absurda_em_apartamento()
    print("ok")
