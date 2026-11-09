import json
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
    assert source_names() == ["calil", "vegas", "zuk", "mega", "lance", "trt5"]


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
        raw_data='{"cidade": "São Paulo", "area": "50 m²", "tipo": "apartamento", "valor_m2_regiao": 12055.0, "valor_mercado_estimado": 602750.0}',
        updated_at=datetime(2026, 9, 17),
    )
    out = lot_to_out(lot, "calil")
    # FipeZap ao vivo (tabela atual), não o valor stale do raw_data.
    assert out.valor_m2_regiao == 12143.0
    assert out.valor_mercado_estimado == 607150.0
    assert out.valor_m2_fonte == "fipezap"


def test_lot_to_out_recalcula_mercado_com_area_reparada():
    """Vegas Jardim Europa: raw com 6908 m² + mercado absurdo → card usa 76,7508."""
    lot = SimpleNamespace(
        id=469,
        auction_id=39,
        external_id="9624",
        title="Apartamento Lagoinha, Rib. Preto/SP",
        description="área total de 76,7508 m², sendo 66,1738 m² de área exclusiva",
        category="Imóvel",
        minimum_bid=99833.5,
        current_bid=99833.5,
        reference_value=None,
        url="https://www.vegasleiloes.com.br/item/9624/detalhes",
        raw_data=json.dumps(
            {
                "cidade": "Ribeirão Preto",
                "tipo": "apartamento",
                "area": "6908 m²",
                "valor_m2_regiao": 5344.0,
                "valor_m2_fonte": "fipezap",
                "valor_mercado_estimado": 36916352.0,
            }
        ),
        updated_at=datetime(2026, 11, 9),
    )
    out = lot_to_out(lot, "vegas")
    assert out.area == "76,7508 m²"
    assert out.valor_mercado_estimado == round(5344.0 * 76.7508, 2)


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
        raw_data='{"avaliado_em": "2026-09-17T20:00:00Z", "score": 62, "score_tem_comparacao_preco": false, "score_motivos": ["sem referência de preço pra comparar — score calculado só com risco/praça", "já na 2ª praça — desconto judicial maior, mas prazo mais curto"]}',
        updated_at=datetime(2026, 9, 17),
    )
    out = lot_to_out(lot, "lance")
    assert out.veredito in ("falta_peca", "aprofundar")
    assert out.ledger
    assert any(i.get("id") == "V3" for i in out.ledger)


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
    assert out.veredito == "falta_peca"
    assert out.veredito_titulo == "Sem norte"
    assert out.veredito_corpo and "Sem norte" in out.veredito_corpo
    assert out.ledger == []
    assert out.score is None
    assert out.avaliado_em is None


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


def test_lot_to_out_exposes_infosimples():
    lot = SimpleNamespace(
        id=9,
        auction_id=9,
        external_id="tjsp-1",
        title="Apto judicial",
        description=None,
        category="Apartamento",
        minimum_bid=200000,
        current_bid=200000,
        reference_value=400000,
        url=None,
        raw_data='{"infosimples": "ok", "infosimples_foro": "Foro Central", "infosimples_valor_causa": 5000.0, "infosimples_peticoes_recentes": [{"data": "12/08/2026", "tipo": "Manifestação do Perito"}]}',
        updated_at=datetime(2026, 9, 17),
    )
    out = lot_to_out(lot, "calil")
    assert out.infosimples == "ok"
    assert out.infosimples_foro == "Foro Central"
    assert out.infosimples_valor_causa == 5000.0
    assert out.infosimples_peticoes_recentes[0]["tipo"] == "Manifestação do Perito"


def test_lot_to_out_exposes_trechos():
    lot = SimpleNamespace(
        id=10,
        auction_id=9,
        external_id="tjsp-2",
        title="Apto judicial",
        description=None,
        category="Apartamento",
        minimum_bid=200000,
        current_bid=200000,
        reference_value=400000,
        url=None,
        raw_data='{"trechos": [{"tipo": "ocupacao", "texto": "Imóvel desocupado.", "origem": "pagina"}]}',
        updated_at=datetime(2026, 9, 17),
    )
    out = lot_to_out(lot, "calil")
    assert out.trechos[0]["tipo"] == "ocupacao"
    assert out.trechos[0]["origem"] == "pagina"


def test_lot_to_out_recalcula_ledger_na_leitura():
    lot = SimpleNamespace(
        id=11,
        auction_id=9,
        external_id="818011",
        title="Casa",
        description=None,
        category="Imóvel",
        minimum_bid=100000,
        current_bid=100000,
        reference_value=None,
        url=None,
        raw_data='{"avaliado_em": "2026-09-17T20:00:00Z", "veredito": "aprofundar", "veredito_titulo": "Aprofundar", "ledger": [{"id": "V1", "lado": "vantagem", "titulo": "Desconto", "frase": "já gravado", "fonte": "laudo", "pontos": 20}], "score": 88, "datajud": "ok"}',
        updated_at=datetime(2026, 9, 17),
    )
    out = lot_to_out(lot, "calil")
    assert out.score != 88
    assert out.regime == "judicial"
    assert all(i.get("frase") != "já gravado" for i in out.ledger)
    assert any(i.get("titulo") == "Sem referência de preço" for i in out.ledger)


def test_lot_to_out_nao_pede_peca_ja_lida():
    raw = {
        "avaliado_em": "2026-09-21T15:00:00Z",
        "cidade": "Ribeirão Preto",
        "valor_mercado_estimado": 242029.76,
        "processo_cnj": "1042707-44.2016.8.26.0506",
        "docs": [
            {"tipo": "matricula", "label": "Matrícula Imóvel - 144.612", "ocr": True, "chars": 3111},
            {"tipo": "edital", "label": "Edital", "chars": 32364},
        ],
        "riscos": {
            "usufruto": True,
            "usufruto_confianca": "baixa",
            "processo_cnj": "1042707-44.2016.8.26.0506",
        },
        "dividas": {"iptu": 274.72},
        "parecer": "Contra: confirmar na matrícula. Sem edital/matrícula. No extrajudicial o IPTU.",
    }
    lot = SimpleNamespace(
        id=120,
        auction_id=1,
        external_id="1555",
        title="Apartamento Magnólia com fração ideal de terreno",
        description="Área real privada de 45,29 m²",
        category="Apartamento",
        minimum_bid=104266,
        current_bid=104266,
        reference_value=None,
        url=None,
        raw_data=json.dumps(raw, ensure_ascii=False),
        updated_at=datetime(2026, 9, 21),
    )
    out = lot_to_out(lot, "calil")
    texto = f"{out.parecer or ''} " + " ".join(i.get("frase") or "" for i in out.ledger)
    assert "confirmar na matrícula" not in texto
    assert "Sem edital/matrícula" not in texto
    assert "extrajudicial" not in texto
    assert not any(i.get("id") == "R2" for i in out.ledger)


if __name__ == "__main__":
    test_lot_to_out_exposes_source_and_cidade()
    test_registry_sources_are_catalog_tabs()
    test_lot_to_out_exposes_market_reference_when_present()
    test_lot_to_out_recalcula_mercado_com_area_reparada()
    test_lot_to_out_market_reference_absent_is_none_not_zero()
    test_lot_to_out_exposes_score_when_present()
    test_lot_to_out_score_absent_defaults_to_empty_motivos()
    test_lot_to_out_exposes_riscos_juridicos()
    test_lot_to_out_usa_preco_da_pagina()
    test_lot_to_out_exposes_pracas()
    test_lot_to_out_exposes_infosimples()
    test_lot_to_out_exposes_trechos()
    test_lot_to_out_recalcula_ledger_na_leitura()
    test_lot_to_out_nao_pede_peca_ja_lida()
    print("ok")
