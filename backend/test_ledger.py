from datetime import date

from app.ledger import DOCUMENTOS, compute_ledger, motivo_sem_peca, regime_of
from app.scoring import apply_score, compute_score


def test_matriz_nao_afirma_sem_documento():
    assert "anuncio" not in DOCUMENTOS["veto"]
    assert "fipezap" in DOCUMENTOS["V1"]
    assert "matricula" in DOCUMENTOS["R2"]


def test_regime_trt5_e_texto():
    assert regime_of("trt5") == "trabalhista"
    assert regime_of(origem="extrajudicial") == "extrajudicial"
    assert regime_of(title="Leilão judicial TJSP") == "judicial"
    assert regime_of(title="Casa em Formiga") == "indefinido"


def test_score_nao_renormaliza():
    so_praca = compute_ledger(title="Lote em 2ª Praça")
    com_preco = compute_ledger(
        title="Lote em 2ª Praça",
        current_bid=100000,
        valor_mercado_estimado=250000,
    )
    assert so_praca["score"] == 50
    assert com_preco["score"] == 70
    assert so_praca["veredito"] == "falta_peca"
    assert com_preco["veredito"] == "aprofundar"


def test_veto_citacao_nao_mistura_com_desconto():
    info = compute_ledger(
        title="Apartamento",
        current_bid=100000,
        valor_mercado_estimado=400000,
        ocupacao="desocupado",
        riscos={"citacao": "nao_citado", "nao_entrar": True},
    )
    assert info["veredito"] == "nao_aprofundar"
    assert info["score"] <= 12
    assert info["itens"][0]["lado"] == "veto"


def test_usufruto_confirmado_e_falta_peca_nao_veto():
    info = compute_ledger(
        title="Casa",
        current_bid=100000,
        valor_mercado_estimado=400000,
        riscos={"usufruto": True, "usufruto_confianca": "alta"},
    )
    assert info["veredito"] == "falta_peca"
    assert info["score"] > 12
    assert any(i["id"] == "R2" and i["pontos"] == -18 for i in info["itens"])


def test_usufruto_eventual_nao_cita_hedge():
    info = compute_ledger(
        title="Apartamento Magnólia",
        current_bid=100000,
        valor_mercado_estimado=242000,
        avaliado=True,
        riscos={
            "usufruto": True,
            "usufruto_confianca": "baixa",
            "usufruto_trecho": "EVENTUAL(IS) TITULAR(ES) DE USUFRUTO, USO, HABITAÇÃO",
        },
    )
    assert not any(i["id"] == "R2" for i in info["itens"])
    assert not any("confirmar na matrícula" in (i.get("frase") or "") for i in info["itens"])


def test_usufruto_eventual_pede_matricula_so_se_peca_faltou():
    info = compute_ledger(
        title="Apartamento Magnólia",
        current_bid=100000,
        valor_mercado_estimado=242000,
        avaliado=True,
        riscos={
            "usufruto": True,
            "usufruto_confianca": "baixa",
            "docs_limitados": True,
        },
    )
    r2 = next(i for i in info["itens"] if i["id"] == "R2")
    assert "confirmar na matrícula" in r2["frase"]


def test_fracao_ideal_nao_finge_falta_de_peca():
    tem = compute_ledger(
        title="Apartamento com fração ideal de terreno",
        current_bid=100000,
        valor_mercado_estimado=242000,
        avaliado=True,
        riscos={},
    )
    falta = compute_ledger(
        title="Apartamento com fração ideal de terreno",
        current_bid=100000,
        valor_mercado_estimado=242000,
        avaliado=True,
        riscos={"docs_limitados": True},
    )
    assert not any("Sem edital/matrícula" in (i.get("frase") or "") for i in tem["itens"])
    assert any("Sem edital/matrícula" in (i.get("frase") or "") for i in falta["itens"])


def test_extra_no_meio_da_palavra_nao_e_extrajudicial():
    assert regime_of(title="Praça extraordinária em Ribeirão") == "indefinido"
    assert regime_of(title="Leilão extrajudicial Caixa") == "extrajudicial"


def test_v3_nao_soma_desconto():
    sem = compute_ledger(title="Lote em 1ª Praça", current_bid=100000, valor_mercado_estimado=200000)
    com = compute_ledger(title="Lote em 2ª Praça", current_bid=100000, valor_mercado_estimado=200000)
    assert sem["score"] == com["score"]
    assert any(i["id"] == "V3" and i["pontos"] == 0 for i in com["itens"])


def test_iptu_nao_pontua():
    info = compute_ledger(
        title="Casa em rua",
        current_bid=200000,
        valor_mercado_estimado=400000,
        origem="judicial",
        dividas={"iptu": 80000},
        tem_divida=False,
    )
    assert all(i["id"] != "R5" or i.get("pontos", 0) == 0 for i in info["itens"] if i["titulo"] == "IPTU")
    assert any("Tema 1.134" in i["frase"] for i in info["itens"] if i["titulo"] == "IPTU")


def test_ocupacao_hipotetica_nao_vira_r4():
    info = compute_ledger(
        title="Terreno",
        description="Caso o imóvel esteja ocupado, a desocupação dependerá de mandado.",
        current_bid=100000,
        valor_mercado_estimado=200000,
        ocupacao="ocupado",
        avaliado=True,
    )
    assert all(i.get("id") != "R4" for i in info["itens"])
    assert any(i.get("titulo") == "Sem ocupação" for i in info["itens"])


def test_laudo_com_menos_de_um_ano_nao_emite_v2():
    info = compute_ledger(
        title="Casa",
        current_bid=100000,
        reference_value=200000,
        fonte_avaliacao="laudo",
        avaliacao_data="2026-08-01",
        hoje=date(2026, 9, 21),
    )
    assert all(i.get("id") != "V2" for i in info["itens"])


def test_sem_lance_ainda_tem_ledger():
    info = compute_ledger(title="Lote TRT", source="trt5")
    assert info["regime"] == "trabalhista"
    assert any(i.get("titulo") == "Sem lance publicado" for i in info["itens"])
    assert info["veredito"] == "falta_peca"


def test_cinquenta_por_cento_da_avaliacao_nao_vira_r3():
    info = compute_ledger(
        title="Casa",
        current_bid=80000,
        valor_mercado_estimado=200000,
        riscos={"meacao": True, "meacao_trecho": "Valor de 50% da avaliação do imóvel: R$ 180.000,00"},
    )
    assert all(i.get("id") != "R3" for i in info["itens"])


def test_overpay_sem_vantagem_e_falta_peca():
    info = compute_ledger(
        title="Casa",
        current_bid=400000,
        valor_mercado_estimado=100000,
    )
    assert any(i.get("id") == "V1" and i.get("lado") == "risco" for i in info["itens"])
    assert info["veredito"] == "falta_peca"


def test_datajud_ok_define_regime_judicial():
    info = compute_ledger(
        title="Casa em Formiga",
        current_bid=80000,
        valor_mercado_estimado=200000,
        riscos={"datajud": "ok"},
    )
    assert info["regime"] == "judicial"
    assert all(i.get("titulo") != "Regime do leilão" for i in info["itens"])


def test_docs_limitados_nao_abre_como_oportunidade():
    info = compute_ledger(
        title="Apartamento",
        current_bid=100000,
        valor_mercado_estimado=242000,
        avaliado=True,
        riscos={"docs_limitados": True, "sem_norte_motivo": "sem_peca_publica"},
    )
    assert info["veredito"] == "falta_peca"
    assert info["veredito_titulo"] == "Sem norte"
    assert "página pública" in info["veredito_corpo"]


def test_docs_limitados_com_veto_continua_nao_aprofundar():
    info = compute_ledger(
        title="Apartamento",
        current_bid=100000,
        valor_mercado_estimado=242000,
        avaliado=True,
        riscos={"docs_limitados": True, "citacao": "nao_citado", "sem_norte_motivo": "trt_so_edital"},
    )
    assert info["veredito"] == "nao_aprofundar"


def test_ocr_curto_fica_como_incerteza_e_nao_vira_oportunidade():
    info = compute_ledger(
        title="Apartamento",
        current_bid=100000,
        valor_mercado_estimado=242000,
        avaliado=True,
        riscos={
            "docs_limitados": True,
            "sem_norte_motivo": "scan_insuficiente",
            "ocr_curto": True,
            "ocr_curto_trecho": "Rua A, 10",
        },
    )
    item = next(i for i in info["itens"] if i.get("titulo") == "Leitura curta")
    assert item["lado"] == "incerteza"
    assert item["confianca"] == "baixa"
    assert item["trecho"] == "Rua A, 10"
    assert info["veredito"] == "falta_peca"
    assert info["veredito_titulo"] == "Sem norte"


def test_ocr_curto_nao_conta_como_peca_util():
    from app.orquestrador import _ler_um, _tem_peca_util

    def ocr(_data, max_pages=2):
        return "Rua A, 10"

    item, text, scanned = _ler_um(b"nao-e-pdf", {"tipo": "matricula", "label": "m.pdf"}, ocr)
    assert text == "Rua A, 10"
    assert scanned is True
    assert item.get("ocr_curto") is True
    assert item.get("confianca") == "baixa"
    assert item.get("trecho") == "Rua A, 10"
    assert _tem_peca_util([item]) is False


def test_fonte_de_mercado_desconhecida_nao_entra_na_conta():
    info = compute_ledger(
        title="Apartamento",
        current_bid=100000,
        valor_mercado_estimado=242000,
        valor_m2_fonte="chute",
        avaliado=True,
    )
    assert info["tem_comparacao_preco"] is False
    assert info["veredito"] != "aprofundar"


def test_motivo_sem_peca_distingue_scan_e_trt():
    assert motivo_sem_peca([{"tipo": "matricula", "scanned": True, "chars": 10}], "calil") == "scan_insuficiente"
    assert motivo_sem_peca([], "trt5") == "trt_so_edital"
    assert motivo_sem_peca([], "vegas") == "sem_peca_publica"


def test_apply_score_grava_ledger():
    extra = {}
    apply_score(extra, compute_score(title="Casa", current_bid=80000, valor_mercado_estimado=200000))
    assert extra["veredito"] == "aprofundar"
    assert extra["ledger"]
    assert isinstance(extra["score"], int)


if __name__ == "__main__":
    test_matriz_nao_afirma_sem_documento()
    test_regime_trt5_e_texto()
    test_score_nao_renormaliza()
    test_veto_citacao_nao_mistura_com_desconto()
    test_usufruto_confirmado_e_falta_peca_nao_veto()
    test_usufruto_eventual_nao_cita_hedge()
    test_usufruto_eventual_pede_matricula_so_se_peca_faltou()
    test_fracao_ideal_nao_finge_falta_de_peca()
    test_extra_no_meio_da_palavra_nao_e_extrajudicial()
    test_v3_nao_soma_desconto()
    test_iptu_nao_pontua()
    test_ocupacao_hipotetica_nao_vira_r4()
    test_laudo_com_menos_de_um_ano_nao_emite_v2()
    test_sem_lance_ainda_tem_ledger()
    test_cinquenta_por_cento_da_avaliacao_nao_vira_r3()
    test_overpay_sem_vantagem_e_falta_peca()
    test_datajud_ok_define_regime_judicial()
    test_docs_limitados_nao_abre_como_oportunidade()
    test_docs_limitados_com_veto_continua_nao_aprofundar()
    test_ocr_curto_fica_como_incerteza_e_nao_vira_oportunidade()
    test_ocr_curto_nao_conta_como_peca_util()
    test_fonte_de_mercado_desconhecida_nao_entra_na_conta()
    test_motivo_sem_peca_distingue_scan_e_trt()
    test_apply_score_grava_ledger()
    print("ok")
