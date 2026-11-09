from app.trechos import coletar_trechos


def test_ocupacao_na_pagina_tem_origem_pagina():
    out = coletar_trechos(page_text="Imóvel desocupado.", blob="")
    assert len(out) == 1
    assert out[0]["tipo"] == "ocupacao"
    assert out[0]["origem"] == "pagina"
    assert "desocupad" in out[0]["texto"].lower()


def test_ocupacao_no_pdf_usa_prefixo_do_documento():
    out = coletar_trechos(
        page_text="",
        blob="[laudo] Laudo de avaliação pericial R$ 400.000,00. Imóvel desocupado.",
    )
    tipos = {t["tipo"]: t for t in out}
    assert tipos["ocupacao"]["origem"] == "laudo"
    assert "desocupad" in tipos["ocupacao"]["texto"].lower()
    assert tipos["avaliacao"]["origem"] == "laudo"
    assert "400.000" in tipos["avaliacao"]["texto"]


def test_pagina_ganha_do_pdf_na_ocupacao():
    out = coletar_trechos(
        page_text="Imóvel desocupado.",
        blob="[edital] Imóvel ocupado pelo executado.",
    )
    occ = next(t for t in out if t["tipo"] == "ocupacao")
    assert occ["origem"] == "pagina"
    assert "desocupad" in occ["texto"].lower()


def test_meacao_reusa_trecho_do_risco():
    out = coletar_trechos(
        riscos={"meacao": True, "meacao_trecho": "Penhora da meação do executado sobre o imóvel"}
    )
    item = next(t for t in out if t["tipo"] == "meacao")
    assert "meação" in item["texto"].lower()
    assert item["origem"] == "edital"


def test_valor_causa_vem_do_infosimples():
    out = coletar_trechos(valor_causa=5000.0)
    item = next(t for t in out if t["tipo"] == "valor_causa")
    assert item["origem"] == "infosimples"
    assert "5.000,00" in item["texto"]


def test_ocr_marca_origem_quando_o_doc_foi_lido_por_visao():
    out = coletar_trechos(
        blob="[edital] Imóvel desocupado.",
        stored_docs=[{"tipo": "edital", "ocr": True, "chars": 120}],
    )
    assert next(t for t in out if t["tipo"] == "ocupacao")["origem"] == "ocr"


def test_sem_frase_nao_inventa_ocupacao():
    assert coletar_trechos(page_text="Casa em Sertãozinho.", blob="[edital] Matrícula 12.345.") == []


def test_magnolia_ocupacao_hipotetica_nao_vira_trecho():
    out = coletar_trechos(
        blob=(
            "[edital] minadas pelo Juízo. § 3º: Caso o imóvel esteja ocupado, "
            "a desocupação dependerá de expedição de mandado."
        )
    )
    assert all(t["tipo"] != "ocupacao" for t in out)


def test_magnolia_usufruto_eventual_nao_vira_trecho():
    out = coletar_trechos(
        blob=(
            "[edital] COPROPRIETÁRIO(S); EVENTUAL(IS) TITULAR(ES) DE USUFRUTO, "
            "USO, HABITAÇÃO, ENFITEUSE, DIREITO DE SUPERFÍCIE"
        )
    )
    assert all(t["tipo"] != "usufruto" for t in out)


def test_trecho_traz_peca_e_ocr():
    out = coletar_trechos(
        blob="[matricula] Imóvel desocupado. Área privativa: 41,85 m².",
        stored_docs=[{"tipo": "matricula", "label": "Matrícula Imóvel - 144.612", "ocr": True, "paginas": 4, "chars": 900}],
    )
    occ = next(t for t in out if t["tipo"] == "ocupacao")
    assert occ["peca"] == "Matrícula Imóvel - 144.612"
    assert occ["ocr"] is True
    assert occ["pagina"] == 4
    assert not occ["texto"].startswith(")")


def test_area_prefere_matricula_mesmo_com_texto_na_pagina():
    out = coletar_trechos(
        page_text="Área real privada de 45,29 m² no anúncio.",
        blob=(
            "[edital] Área real privada de 45,29 m² no edital. "
            "[matricula] com a área real privada de 45,29 m² e área real comum de 6,25 m²."
        ),
        stored_docs=[
            {"tipo": "edital", "label": "Edital"},
            {
                "tipo": "matricula",
                "label": "Matrícula Imóvel - 144.612",
                "ocr": True,
                "paginas": 4,
            },
        ],
    )
    area = next(t for t in out if t["tipo"] == "area")
    assert area["peca"] == "Matrícula Imóvel - 144.612"
    assert area["ocr"] is True
    assert area["origem"] == "ocr"
    assert "45,29" in area["texto"]


def test_trecho_longo_sem_ponto_mantem_o_match():
    capa = "24 - REGISTRO GERAL IMÓVEL: O apartamento nº 32-A " + ("localizado no bloco C " * 12)
    blob = f"[matricula] {capa} com a área real privada de 45,29 m² e área real comum de 6,25 m²."
    out = coletar_trechos(blob=blob)
    area = next(t for t in out if t["tipo"] == "area")
    assert "45,29" in area["texto"]
    assert not area["texto"].startswith("24 - REGISTRO")


if __name__ == "__main__":
    test_ocupacao_na_pagina_tem_origem_pagina()
    test_ocupacao_no_pdf_usa_prefixo_do_documento()
    test_pagina_ganha_do_pdf_na_ocupacao()
    test_meacao_reusa_trecho_do_risco()
    test_valor_causa_vem_do_infosimples()
    test_ocr_marca_origem_quando_o_doc_foi_lido_por_visao()
    test_sem_frase_nao_inventa_ocupacao()
    test_magnolia_ocupacao_hipotetica_nao_vira_trecho()
    test_magnolia_usufruto_eventual_nao_vira_trecho()
    test_trecho_traz_peca_e_ocr()
    test_area_prefere_matricula_mesmo_com_texto_na_pagina()
    test_trecho_longo_sem_ponto_mantem_o_match()
    print("ok")
