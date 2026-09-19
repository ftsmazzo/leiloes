from pathlib import Path

from app.edital import (
    avaliar_lote,
    avaliacao_data_from_text,
    collect_pdfs,
    fields_from_text,
    parecer_from_facts,
)
from app.scrapers.extract import leilao_status
from app.scrapers.soleon import lots_from_imovel_list
from app.scoring import compute_score

ROOT = Path(__file__).resolve().parent
HTML = (ROOT / "fixtures" / "edital_links.html").read_text(encoding="utf-8")


def test_collect_pdfs_keeps_edital_skips_privacy():
    docs = collect_pdfs(HTML, "https://www.calilleiloes.com.br/item/1582/detalhes")
    tipos = [d["tipo"] for d in docs]
    urls = [d["url"] for d in docs]
    assert "laudo" in tipos
    assert "edital" in tipos
    assert "debito" in tipos
    assert all("privacidade" not in u.lower() for u in urls)
    assert all("proposta" not in u.lower() for u in urls)
    assert docs[0]["tipo"] == "laudo"


def test_fields_from_text_read_avaliacao_ocupacao_divida():
    blob = (
        "Laudo de avaliação pericial no valor de R$ 400.000,00. "
        "Imóvel desocupado. Débitos de condomínio R$ 12.500,00 e IPTU R$ 3.200,00."
    )
    fields = fields_from_text(blob)
    assert fields["avaliacao_edital"] == 400000
    assert fields["ocupacao"] == "desocupado"
    assert fields["tem_divida"] is True
    assert fields["dividas"]["condominio"] == 12500
    assert fields["dividas"]["iptu"] == 3200


def test_fields_iptu_sozinho_nao_e_divida_que_pesa():
    fields = fields_from_text("IPTU em dívida ativa R$ 8.000,00. Imóvel desocupado.")
    assert fields["dividas"]["iptu"] == 8000
    assert fields.get("dividas", {}).get("condominio") is None
    assert fields["tem_divida"] is False


IPTU_CADASTRO = """
Matrícula: 0045170 - 2º Cartório de Registro de Imóveis
Inscrição Cadastral: 441-13-77-2
Logradouro: Rua Amador Bueno, n°. 253
Complemento: AP 101
Bairro: Centro
CEP: 14.010-070
Área do terreno: 16,07 m²
Valor venal do terreno: R$ 15.323,22
Edificação principal: 83,29 m²
Valor venal edificação principal: R$ 84.432,73
Valor venal do imóvel: R$ 99.755,95
"""


def test_fields_from_text_usa_venal_do_imovel_nao_do_terreno():
    fields = fields_from_text(IPTU_CADASTRO)
    assert fields["avaliacao_edital"] == 99755.95
    assert fields["avaliacao_fonte"] == "venal_imovel"
    assert fields["valor_venal_terreno"] == 15323.22
    assert fields["valor_venal_edificacao"] == 84432.73
    assert fields["area_edificacao"] == 83.29
    assert fields["area_terreno"] == 16.07
    assert "83,29" in fields["area"]


def test_score_venal_acima_nao_conta_como_overpay():
    result = compute_score(
        title="Apartamento Centro",
        current_bid=198235.60,
        reference_value=99755.95,
        fonte_avaliacao="venal_imovel",
        dividas={"condominio": 185.97},
    )
    assert result["tem_comparacao_preco"] is False
    assert result["fonte_avaliacao"] == "venal_imovel"
    assert any("não conta como overpay" in m for m in result["motivos"])
    assert any("impacto baixo" in m for m in result["motivos"])
    assert result["score"] >= 40


def test_score_com_edital_sobe_quando_ha_desconto_e_desocupado():
    sem = compute_score(title="Apartamento", current_bid=202408.70)
    com = compute_score(
        title="Apartamento",
        current_bid=202408.70,
        reference_value=400000,
        ocupacao="desocupado",
        tem_divida=False,
    )
    assert sem["tem_comparacao_preco"] is False
    assert com["tem_comparacao_preco"] is True
    assert com["score"] > sem["score"]
    assert com["score"] >= 75


def test_parecer_from_facts_nao_inventa_numero():
    text = parecer_from_facts(
        {
            "score": 83,
            "tem_comparacao_preco": True,
            "motivos": ["49% abaixo da avaliação do edital", "desocupado (declarado no edital)"],
            "docs": [{"label": "Edital", "tipo": "edital"}],
            "status": "aberto",
            "lance_atual": 198235.6,
        }
    )
    assert "83/100" in text
    assert "Edital" in text
    assert "imperdível" not in text.lower()
    assert "arrematad" not in text.lower()


def test_leilao_status_nao_confunde_arrematante_com_vendido():
    assert leilao_status("Aguarde Abertura Lance Inicial R$198.235,60") == "aguardando"
    assert leilao_status("Lote encerrado") == "encerrado"
    assert leilao_status("Imóvel arrematado em 10/09") == "encerrado"
    assert leilao_status("O arrematante deverá quitar o saldo") == "aberto"


def test_imovel_list_skips_arrematado():
    html = """
    <div class="lote"><a href="/item/1/detalhes"><h5>Casa aberta</h5>
    <div class="label_lote aberto_lance">Aberto para Lances</div>
    <h4 class="mb-0">R$100.000,00</h4></a></div>
    <div class="lote"><a href="/item/2/detalhes"><h5>Casa vendida</h5>
    <div>Lote encerrado — arrematado</div>
    <h4 class="mb-0">R$90.000,00</h4></a></div>
    """
    lots = lots_from_imovel_list(html, "https://www.calilleiloes.com.br")
    assert [lot.external_id for lot in lots] == ["1"]


def test_parecer_aguardando_nao_diz_arrematado():
    text = parecer_from_facts(
        {
            "score": 38,
            "status": "aguardando",
            "lance_atual": 198235.6,
            "motivos": ["sem referência de preço pra comparar — score calculado só com risco/praça"],
        }
    )
    assert "ainda não abriu" in text.lower()
    assert "arrematad" not in text.lower()


def test_avaliar_lote_usa_fixture_sem_rede():
    pdf_blob = (
        "Avaliação judicial R$ 400.000,00. Imóvel desocupado, sem débitos condominiais."
    )

    def fake_page(_url: str) -> str:
        return HTML

    def fake_file(_url: str) -> bytes:
        return b"%PDF-1.4 fake"

    extra = avaliar_lote(
        title="Apartamento em Ribeirão Preto",
        description=None,
        url="https://www.calilleiloes.com.br/item/1582/detalhes",
        current_bid=202408.70,
        minimum_bid=202408.70,
        reference_value=None,
        extra={"cidade": "Ribeirão Preto"},
        fetch_page=fake_page,
        fetch_file=fake_file,
        write_ai=False,
    )
    assert extra["docs"]
    assert extra["avaliado_em"]
    assert extra["parecer"]
    assert extra["score"] >= 0
    # PDF fake não tem texto — score pode continuar parcial
    assert "docs" in extra


def test_avaliar_lote_com_texto_recalcula_score(monkeypatch=None):
    from app import edital as edital_mod

    original = edital_mod.extract_pdf_text

    def fake_extract(_data: bytes):
        return (
            "Laudo de avaliação pericial R$ 400.000,00. Imóvel desocupado.",
            False,
        )

    edital_mod.extract_pdf_text = fake_extract
    try:
        extra = avaliar_lote(
            title="Apartamento",
            description=None,
            url="https://example.test/item/1",
            current_bid=202408.70,
            minimum_bid=202408.70,
            reference_value=None,
            extra={},
            fetch_page=lambda _u: HTML,
            fetch_file=lambda _u: b"%PDF-1.4 x",
            write_ai=False,
        )
        assert extra["avaliacao_edital"] == 400000
        assert extra["ocupacao"] == "desocupado"
        assert extra["score_tem_comparacao_preco"] is True
        assert extra["score"] > 50
        assert "400" in extra["parecer"] or "abaixo" in extra["parecer"].lower() or "Score" in extra["parecer"]
    finally:
        edital_mod.extract_pdf_text = original


def test_data_laudo_ignora_edital_e_condominio():
    blob = (
        "Edital publicado em 10/09/2026. "
        "Débito condominial referência a maio de 2023 R$ 185,97. "
        "Data da avaliação: 03/04/2015. Laudo de avaliação pericial R$ 400.000,00."
    )
    fields = fields_from_text(blob)
    assert fields["avaliacao_data"] == "2015-04-03"
    assert fields["avaliacao_data_origem"] == "laudo"
    so_data = avaliacao_data_from_text(
        "Processo n. 0001234-11.2012.8.26.0000 distribuído em 22/11/2012. Sem laudo."
    )
    assert so_data["avaliacao_data"] == "2012-11-22"
    assert so_data["avaliacao_data_origem"] == "processo"


if __name__ == "__main__":
    test_collect_pdfs_keeps_edital_skips_privacy()
    test_fields_from_text_read_avaliacao_ocupacao_divida()
    test_fields_iptu_sozinho_nao_e_divida_que_pesa()
    test_fields_from_text_usa_venal_do_imovel_nao_do_terreno()
    test_score_venal_acima_nao_conta_como_overpay()
    test_score_com_edital_sobe_quando_ha_desconto_e_desocupado()
    test_parecer_from_facts_nao_inventa_numero()
    test_leilao_status_nao_confunde_arrematante_com_vendido()
    test_imovel_list_skips_arrematado()
    test_parecer_aguardando_nao_diz_arrematado()
    test_avaliar_lote_usa_fixture_sem_rede()
    test_avaliar_lote_com_texto_recalcula_score()
    test_data_laudo_ignora_edital_e_condominio()
    print("ok")
