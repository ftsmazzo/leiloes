import os

from app.apify_mercado import (
    _resultado,
    chave_consulta,
    consultar_apify,
    location_input,
    locations_to_try,
    mediana,
    ppm2_dos_anuncios,
)
from app.edital import avaliar_lote

os.environ.pop("INFOSIMPLES_API_TOKEN", None)
os.environ.pop("GLINER_URL", None)
os.environ.pop("GLINER_API_TOKEN", None)
os.environ.pop("APIFY_TOKEN", None)
os.environ.pop("APIFY_API_TOKEN", None)
os.environ.pop("OPENROUTER_API_KEY", None)


def test_location_terreno_usa_cidade_o_actor_nao_traz_terreno_filtrado():
    url = location_input("Brodowski", "terreno", "0000467-17.2025.8.26.0094")
    assert url == "https://www.vivareal.com.br/venda/sp/brodowski/"


def test_location_casa_mantem_tipo_no_path():
    url = location_input("Brodowski", "casa", "0000467-17.2025.8.26.0094")
    assert url == "https://www.vivareal.com.br/venda/sp/brodowski/casa_residencial/"


def test_locations_terreno_nao_repete_path_que_o_actor_zera():
    locs = locations_to_try("Brodowski", "terreno", "0000467-17.2025.8.26.0094")
    assert locs[0] == "https://www.vivareal.com.br/venda/sp/brodowski/"
    assert all("terreno_residencial" not in loc for loc in locs)


def test_location_sem_cnj_usa_nome_da_cidade():
    assert location_input("Formiga", "casa") == "Formiga"


def test_mediana_exige_tres_anuncios():
    assert mediana([100.0, 200.0]) is None
    assert mediana([100.0, 200.0, 300.0]) == 200.0


def test_ppm2_ignora_aluguel_e_area_miuda():
    items = [
        {"listingType": "SALE", "price": 400000, "usableArea": 80},
        {"listingType": "RENTAL", "price": 2500, "usableArea": 80},
        {"listingType": "SALE", "price": 5000, "usableArea": 80},
        {"listingType": "SALE", "price": 450000, "usableArea": 10},
    ]
    apto = ppm2_dos_anuncios(items, "apartamento")
    assert apto == [5000.0]
    terreno = ppm2_dos_anuncios(
        [{"listingType": "SALE", "price": 450000, "totalArea": 500}],
        "terreno",
    )
    assert terreno == [900.0]


def test_sem_token_nao_quebra():
    from app import apify_mercado as mod

    orig = mod._api_token
    mod._api_token = lambda: ""
    try:
        assert consultar_apify(cidade="Brodowski", tipo="terreno", area=500) == {}
    finally:
        mod._api_token = orig


def test_fetch_injetado_preenche_mediana_e_cache():
    items = [
        {"listingType": "SALE", "price": 300000, "totalArea": 400},
        {"listingType": "SALE", "price": 360000, "totalArea": 400},
        {"listingType": "SALE", "price": 420000, "totalArea": 400},
        {"listingType": "SALE", "price": 480000, "totalArea": 400},
    ]
    out = consultar_apify(
        cidade="Brodowski",
        tipo="terreno",
        area=500,
        cnj="0000467-17.2025.8.26.0094",
        fetch=lambda _p: items,
    )
    assert out["valor_m2_fonte"] == "apify"
    assert out["valor_m2_regiao"] == 975.0
    assert out["valor_mercado_estimado"] == 487500.0
    assert out["valor_m2_n"] == 4
    assert out["apify_consultado_para"] == chave_consulta("Brodowski", "terreno")
    novamente = consultar_apify(
        cidade="Brodowski",
        tipo="terreno",
        area=500,
        ja_consultado=out["apify_consultado_para"],
        fetch=lambda _p: (_ for _ in ()).throw(AssertionError("não deveria chamar")),
    )
    assert novamente == {}


def test_menos_de_tres_anuncios_nao_inventa():
    out = consultar_apify(
        cidade="Brodowski",
        tipo="terreno",
        area=500,
        fetch=lambda _p: [{"listingType": "SALE", "price": 300000, "totalArea": 400}],
    )
    assert out["apify"] == "poucos"
    assert "valor_mercado_estimado" not in out


def test_avaliar_lote_usa_apify_quando_fipezap_nao_cobre():
    called: list = []

    def fake_apify(payload):
        called.append(payload)
        return [
            {"listingType": "SALE", "price": 200000, "totalArea": 400},
            {"listingType": "SALE", "price": 240000, "totalArea": 400},
            {"listingType": "SALE", "price": 280000, "totalArea": 400},
        ]

    extra = avaliar_lote(
        title="Terreno em Brodowski",
        description=None,
        url="https://example.test/item/1",
        current_bid=100000,
        minimum_bid=100000,
        reference_value=None,
        extra={"cidade": "Brodowski", "tipo": "terreno", "area": "500 m²", "processo_cnj": "0000467-17.2025.8.26.0094"},
        fetch_page=lambda _u: "<html><body>Terreno Brodowski</body></html>",
        fetch_file=lambda _u: b"",
        fetch_datajud=lambda _u, _p: {},
        fetch_apify=fake_apify,
        write_ai=False,
        ocr=lambda _d: "",
    )
    assert called
    assert "brodowski" in called[0]["location"]
    assert extra["valor_m2_fonte"] == "apify"
    assert extra["valor_mercado_estimado"] == 300000.0
    assert extra["apify_consultado_para"] == chave_consulta("Brodowski", "terreno")

    extra2 = avaliar_lote(
        title="Terreno em Brodowski",
        description=None,
        url="https://example.test/item/1",
        current_bid=100000,
        minimum_bid=100000,
        reference_value=None,
        extra={
            "cidade": "Brodowski",
            "tipo": "terreno",
            "area": "500 m²",
            "apify_consultado_para": extra["apify_consultado_para"],
            "valor_m2_fonte": "apify",
            "valor_m2_regiao": extra["valor_m2_regiao"],
            "valor_mercado_estimado": extra["valor_mercado_estimado"],
        },
        fetch_page=lambda _u: "<html><body>Terreno Brodowski</body></html>",
        fetch_file=lambda _u: b"",
        fetch_datajud=lambda _u, _p: {},
        fetch_apify=lambda _p: called.append("nope") or [],
        write_ai=False,
        ocr=lambda _d: "",
    )
    assert extra2["valor_mercado_estimado"] == 300000.0
    assert called[-1] != "nope"


def test_avaliar_lote_apto_em_sao_paulo_nao_chama_apify():
    called: list = []
    extra = avaliar_lote(
        title="Apartamento em São Paulo",
        description=None,
        url="https://example.test/item/1",
        current_bid=200000,
        minimum_bid=200000,
        reference_value=None,
        extra={"cidade": "São Paulo", "tipo": "apartamento", "area": "50 m²"},
        fetch_page=lambda _u: "<html><body>Apto</body></html>",
        fetch_file=lambda _u: b"",
        fetch_datajud=lambda _u, _p: {},
        fetch_apify=lambda _p: called.append(_p) or [],
        write_ai=False,
        ocr=lambda _d: "",
    )
    assert called == []
    assert extra["valor_m2_fonte"] == "fipezap"


def test_apify_com_area_fecha_valor_do_imovel():
    items = [
        {"listingType": "SALE", "price": 200000, "usableArea": 40},
        {"listingType": "SALE", "price": 220000, "usableArea": 40},
        {"listingType": "SALE", "price": 240000, "usableArea": 40},
    ]
    out = _resultado(items, chave="ribeirao-preto|apartamento|venda", tipo="apartamento", area=41.85)
    assert out["valor_m2_n"] == 3
    assert out["valor_m2_regiao"] == 5500.0
    assert out["valor_mercado_estimado"] == round(5500.0 * 41.85, 2)


def test_apify_sem_area_nao_inventa_total():
    items = [
        {"listingType": "SALE", "price": 200000, "usableArea": 40},
        {"listingType": "SALE", "price": 220000, "usableArea": 40},
        {"listingType": "SALE", "price": 240000, "usableArea": 40},
    ]
    out = _resultado(items, chave="x", tipo="apartamento", area=None)
    assert out["valor_m2_n"] == 3
    assert "valor_mercado_estimado" not in out


if __name__ == "__main__":
    test_location_terreno_usa_cidade_o_actor_nao_traz_terreno_filtrado()
    test_location_casa_mantem_tipo_no_path()
    test_locations_terreno_nao_repete_path_que_o_actor_zera()
    test_location_sem_cnj_usa_nome_da_cidade()
    test_mediana_exige_tres_anuncios()
    test_ppm2_ignora_aluguel_e_area_miuda()
    test_sem_token_nao_quebra()
    test_fetch_injetado_preenche_mediana_e_cache()
    test_menos_de_tres_anuncios_nao_inventa()
    test_avaliar_lote_usa_apify_quando_fipezap_nao_cobre()
    test_avaliar_lote_apto_em_sao_paulo_nao_chama_apify()
    test_apify_com_area_fecha_valor_do_imovel()
    test_apify_sem_area_nao_inventa_total()
    print("ok")
