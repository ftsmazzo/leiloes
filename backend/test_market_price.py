from app.scrapers.market_price import estimate_market_value, price_per_m2


def test_price_per_m2_known_city_case_and_accent_insensitive():
    assert price_per_m2("São Paulo") == 12055.0
    assert price_per_m2("sao paulo") == 12055.0
    assert price_per_m2("SÃO PAULO") == 12055.0


def test_price_per_m2_unknown_city_returns_none():
    assert price_per_m2("Formiga") is None
    assert price_per_m2(None) is None
    assert price_per_m2("") is None


def test_estimate_market_value_known_city_and_area():
    result = estimate_market_value("São Paulo", "200 m²")
    assert result == {"valor_m2_regiao": 12055.0, "valor_mercado_estimado": 2411000.0}


def test_estimate_market_value_missing_city_or_area_returns_none():
    assert estimate_market_value(None, "200 m²") is None
    assert estimate_market_value("São Paulo", None) is None
    assert estimate_market_value("Formiga", "200 m²") is None  # cidade sem referência
    assert estimate_market_value("São Paulo", "não numérico") is None


if __name__ == "__main__":
    test_price_per_m2_known_city_case_and_accent_insensitive()
    test_price_per_m2_unknown_city_returns_none()
    test_estimate_market_value_known_city_and_area()
    test_estimate_market_value_missing_city_or_area_returns_none()
    print("ok")
