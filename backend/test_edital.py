from pathlib import Path

from app.orquestrador import snapshot_preco
from app.edital import (
    avaliar_lote,
    avaliacao_data_from_text,
    collect_pdfs,
    extract_pdf_text,
    fields_from_text,
    parecer_from_facts,
    precos_from_page,
)
from app.scrapers.extract import leilao_status
from app.scrapers.soleon import lots_from_imovel_list
from app.scoring import compute_score

ROOT = Path(__file__).resolve().parent
HTML = (ROOT / "fixtures" / "edital_links.html").read_text(encoding="utf-8")


def _pdf_com_texto(texto: str) -> bytes:
    """PDF mínimo, sem xref válido — suficiente pro pypdfium2 ler, imita edital real malformado."""
    content = f"BT /F1 12 Tf 10 100 Td ({texto}) Tj ET".encode("latin-1")
    parts = [
        b"%PDF-1.4\n",
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n",
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n",
        b"3 0 obj<</Type/Page/Parent 2 0 R/Resources<</Font<</F1 4 0 R>>>>/MediaBox[0 0 3000 200]/Contents 5 0 R>>endobj\n",
        b"4 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n",
        b"5 0 obj<</Length " + str(len(content)).encode() + b">>\nstream\n" + content + b"\nendstream\nendobj\n",
        b"trailer<</Size 6/Root 1 0 R>>\n%%EOF",
    ]
    return b"".join(parts)


def test_extract_pdf_text_usa_pypdfium2_quando_pypdf_falha():
    from app import edital as edital_mod

    texto = "EDITAL DE ALIENACAO JUDICIAL POR INICIATIVA PARTICULAR - PROCESSO 0001234-11.2020.5.05.0001"
    data = _pdf_com_texto(texto)
    original = edital_mod._extract_with_pypdf

    def fake_pypdf(_data: bytes):
        raise TypeError("unsupported operand type(s) for += : 'int' and 'IndirectObject'")

    edital_mod._extract_with_pypdf = fake_pypdf
    try:
        text, scanned = extract_pdf_text(data)
        assert texto in text
        assert scanned is False
    finally:
        edital_mod._extract_with_pypdf = original


def test_extract_pdf_text_carimbo_esaj_sozinho_conta_como_escaneado():
    """PDF real do e-SAJ/TJSP: só o carimbo de autenticação é texto, o conteúdo é imagem.
    O carimbo sozinho passa de 80 chars — sem a checagem, o pipeline nunca chamava OCR."""
    carimbo = (
        "SOLICITADO POR: JULIO CALIL - CPF/CNPJ: ***.277.508-** DATA: 14/07/2026 14:28:18\n"
        "Para conferir o original, acesse o site https://esaj.tjsp.jus.br/pastadigital, "
        "informe o processo 1001610-20.2023.8.26.0506 e codigo ABC123.\n"
        "Este documento e copia do original, assinado digitalmente por FULANO DE TAL, "
        "protocolado em 17/07/2026 as 10:47, sob o numero WRPR26703422761.\n"
        "fls. 201"
    )
    data = _pdf_com_texto(carimbo)
    text, scanned = extract_pdf_text(data)
    assert scanned is True


def test_extract_pdf_text_marca_dagua_ridigital_conta_como_escaneado():
    """Matrícula real da Mega vem do RI Digital: só a marca d'água do visualizador é texto."""
    marca = "Visualizacao disponibilizada pelo RI Digital (ridigital.org.br)-Visualizado em:21/07/2026 16:54:50"
    data = _pdf_com_texto(marca)
    text, scanned = extract_pdf_text(data)
    assert scanned is True


def test_extract_pdf_text_sem_fallback_quando_pypdf_ja_funciona():
    texto = "LAUDO PERICIAL DE AVALIACAO JUDICIAL - IMOVEL RESIDENCIAL URBANO MATRICULA 12345"
    data = _pdf_com_texto(texto)
    text, scanned = extract_pdf_text(data)
    assert texto in text
    assert scanned is False


def test_fields_from_text_le_matricula_area_ocupacao_so_da_pagina():
    """Zuk/Lance oferecem pouco PDF público, mas a própria página já tem esses dados
    (evidência real: lote 232155 da Zuk, sem nenhum PDF acessível sem login)."""
    page_text = (
        "Metragem terreno 441,00m² Imóvel ocupado Este imóvel encontra-se ocupado "
        "no momento. Matrícula do imóvel: 6.743 do 1º CRI -  Lorena/SP "
        "Processo: 0119208-38.2001.8.26.0100"
    )
    out = fields_from_text("", page_text, source="zuk")
    assert out["area_terreno"] == 441.0
    assert out["ocupacao"] == "ocupado"
    assert out["matricula_numero"].replace(".", "") == "6743"
    assert "CRI" in out["matricula_cartorio"]
    assert out["processo_cnj"] == "0119208-38.2001.8.26.0100"


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


def test_anexo_de_matricula_tira_analise_limitada():
    from app import edital as edital_mod

    original = edital_mod.extract_pdf_text

    def fake_extract(data: bytes):
        if data.startswith(b"%PDF-ANEXO"):
            return (
                "Laudo de avaliação pericial R$ 400.000,00. Imóvel desocupado. "
                "Matrícula 12.345 sem ônus de usufruto.",
                False,
            )
        return "", True

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
            anexos=[("matricula.pdf", b"%PDF-ANEXO texto")],
            ocr=lambda _d: "",
        )
        assert extra["avaliacao_edital"] == 400000
        assert extra["ocupacao"] == "desocupado"
        assert extra.get("docs_limitados") is None
        assert any(d.get("anexo") and d.get("tipo") == "matricula" for d in extra["docs"])
        assert extra["score"] > 50
    finally:
        edital_mod.extract_pdf_text = original


def test_ocr_no_pdf_publico_escaneado():
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
        ocr=lambda _d: (
            "Laudo de avaliação pericial R$ 400.000,00. Imóvel desocupado. "
            "Sem ônus de usufruto na matrícula."
        ),
    )
    assert extra["avaliacao_edital"] == 400000
    assert extra["ocupacao"] == "desocupado"
    assert any(d.get("ocr") for d in extra["docs"])
    assert extra.get("docs_limitados") is None


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


def test_fields_from_text_le_riscos_do_edital():
    blob = (
        "Processo n. 0001234-11.2012.8.26.0100. O executado não foi citado. "
        "Matrícula com usufruto. Penhora da meação. Laudo R$ 400.000,00."
    )
    fields = fields_from_text(blob)
    assert fields["processo_cnj"] == "0001234-11.2012.8.26.0100"
    assert fields["riscos"]["citacao"] == "nao_citado"
    assert fields["riscos"]["usufruto"] is True
    assert fields["riscos"]["meacao"] is True


def test_fracao_ideal_do_lote_nao_vira_meacao():
    blob = (
        "DIREITOS DA ALIENAÇÃO FIDUCIARIA da unidade autônoma Apartamento nº 34, "
        "área total de 48,383m², fração ideal de 0,357143% do terreno. "
        "O cônjuge do executado será intimado. Bem de família."
    )
    fields = fields_from_text(blob)
    assert "meacao" not in (fields.get("riscos") or {})


def test_precos_from_page_separa_lance_e_avaliacao():
    precos = precos_from_page(
        "Valor atual R$ 25.978,19 Incremento R$ 1.000,00 Valor de avaliação R$ 51.956,37"
    )
    assert precos["lance_pagina"] == 25978.19
    assert precos["avaliacao_pagina"] == 51956.37


def test_precos_from_html_grupo_lance_nao_usa_1a_praca():
    html = (ROOT / "fixtures" / "lance_item.html").read_text(encoding="utf-8")
    precos = precos_from_page(html=html)
    assert precos["lance_pagina"] == 4207866.06
    assert precos["avaliacao_pagina"] == 7013110.1


def test_snapshot_pagina_ganha_do_scrape_da_1a_praca():
    snap = snapshot_preco(
        {"lance_pagina": 4207866.06, "avaliacao_pagina": 7013110.1},
        {"avaliacao_edital": 7013110.1},
        current_bid=7013110.1,
        minimum_bid=7013110.1,
        reference_value=7013110.1,
    )
    assert snap["lance"] == 4207866.06
    assert snap["inicial"] == 4207866.06
    assert snap["avaliacao"] == 7013110.1
    assert snap["fonte"] == "pagina"


def test_avaliar_lote_respeita_valor_atual_da_pagina():
    html = (ROOT / "fixtures" / "lance_item.html").read_text(encoding="utf-8")
    extra = avaliar_lote(
        title="Terreno Porto Ferreira",
        description=None,
        url="https://www.grupolance.com.br/imoveis/terrenos/sp/porto-ferreira/x-28639",
        current_bid=7013110.10,
        minimum_bid=7013110.10,
        reference_value=7013110.10,
        extra={},
        fetch_page=lambda _u: html,
        fetch_file=lambda _u: b"%PDF-1.4 x",
        write_ai=False,
    )
    assert extra["lance_pagina"] == 4207866.06
    assert extra["avaliacao_edital"] == 7013110.1
    assert extra["preco_fonte"] == "pagina"
    assert extra["pracas"][0]["valor"] == 7013110.1
    assert extra["pracas"][1]["valor"] == 4207866.06
    assert extra["pracas"][1]["fim"].startswith("2026-10-20")
    assert extra["score"] > 50
    assert any("40% abaixo" in m for m in extra["score_motivos"])
    assert not any(m.startswith("0% abaixo") for m in extra["score_motivos"])
    assert not any(m.startswith("desocupado") for m in extra["score_motivos"])
    assert not any("sem débitos de condomínio" in m for m in extra["score_motivos"])


def test_parecer_diz_quando_faltou_documento_e_datajud():
    text = parecer_from_facts(
        {
            "score": 55,
            "docs_limitados": True,
            "riscos": {"datajud": "nao_encontrado"},
            "motivos": ["matrícula/laudo sem texto extraível — análise limitada"],
        }
    )
    assert "matrícula" in text.lower() or "limitada" in text.lower()
    assert "DataJud" in text
    assert "não entre" not in text.lower()


def test_avaliar_lote_consulta_datajud_injetado():
    from app import edital as edital_mod

    original = edital_mod.extract_pdf_text

    def fake_extract(_data: bytes):
        return (
            "Processo n. 0001234-11.2012.8.26.0100. O executado não foi citado. "
            "Laudo de avaliação pericial R$ 400.000,00. Imóvel desocupado.",
            False,
        )

    def fake_datajud(_url, _payload):
        return {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "tribunal": "TJSP",
                            "classe": {"nome": "Execução"},
                            "movimentos": [{"nome": "Citação cumprida"}],
                        }
                    }
                ]
            }
        }

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
            fetch_datajud=fake_datajud,
            write_ai=False,
        )
        assert extra["processo_cnj"] == "0001234-11.2012.8.26.0100"
        assert extra["riscos"]["citacao"] == "citado"
        assert extra["riscos"]["citacao_fonte"] == "datajud"
        assert extra.get("nao_entrar") is None
        assert extra["score"] > 12
    finally:
        edital_mod.extract_pdf_text = original


if __name__ == "__main__":
    test_extract_pdf_text_usa_pypdfium2_quando_pypdf_falha()
    test_extract_pdf_text_carimbo_esaj_sozinho_conta_como_escaneado()
    test_extract_pdf_text_marca_dagua_ridigital_conta_como_escaneado()
    test_extract_pdf_text_sem_fallback_quando_pypdf_ja_funciona()
    test_fields_from_text_le_matricula_area_ocupacao_so_da_pagina()
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
    test_anexo_de_matricula_tira_analise_limitada()
    test_ocr_no_pdf_publico_escaneado()
    test_data_laudo_ignora_edital_e_condominio()
    test_fields_from_text_le_riscos_do_edital()
    test_fracao_ideal_do_lote_nao_vira_meacao()
    test_precos_from_page_separa_lance_e_avaliacao()
    test_precos_from_html_grupo_lance_nao_usa_1a_praca()
    test_snapshot_pagina_ganha_do_scrape_da_1a_praca()
    test_avaliar_lote_respeita_valor_atual_da_pagina()
    test_parecer_diz_quando_faltou_documento_e_datajud()
    test_avaliar_lote_consulta_datajud_injetado()
    print("ok")
