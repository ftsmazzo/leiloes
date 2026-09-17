from app.juridico import riscos_from_text


def test_nao_citado_e_cnj():
    riscos = riscos_from_text(
        "Processo n. 0001234-11.2012.8.26.0100. O executado não foi citado. "
        "Leiloeiro público oficial João da Silva."
    )
    assert riscos["citacao"] == "nao_citado"
    assert riscos["nao_entrar"] is True
    assert riscos["processo_cnj"] == "0001234-11.2012.8.26.0100"


def test_cnj_compacto_formata():
    riscos = riscos_from_text("Processo nº 00012341120128260100")
    assert riscos["processo_cnj"] == "0001234-11.2012.8.26.0100"


def test_citado_regularmente_nao_trava():
    riscos = riscos_from_text("O executado foi regularmente citado.")
    assert riscos["citacao"] == "citado"
    assert "nao_entrar" not in riscos


def test_citacao_por_edital():
    riscos = riscos_from_text("Citação por edital do executado.")
    assert riscos["citacao"] == "edital"


def test_usufruto_na_matricula():
    riscos = riscos_from_text("A matrícula registra usufruto vitalício em favor de Maria.")
    assert riscos["usufruto"] is True


def test_livre_de_usufruto_nao_marca():
    riscos = riscos_from_text("Imóvel livre de usufruto e ônus reais.")
    assert "usufruto" not in riscos


def test_meacao_e_conjuge():
    riscos = riscos_from_text("Penhora da meação do executado e de sua cônjuge sobre o imóvel.")
    assert riscos["meacao"] is True
    assert "penhora da meação" in riscos["meacao_trecho"].lower()


def test_conjuge_do_arrematante_nao_e_meacao():
    riscos = riscos_from_text("O cônjuge do arrematante deverá anuir à carta.")
    assert "meacao" not in riscos


def test_fracao_ideal_do_condominio_nao_e_meacao():
    riscos = riscos_from_text(
        "Apartamento nº 34, área total de 48,383m², fração ideal de 0,357143% do terreno; "
        "o cônjuge do executado será intimado nos termos do art. 842 do CPC. "
        "Bem de família e comunhão parcial de bens conforme a lei."
    )
    assert "meacao" not in riscos


def test_regra_generica_de_conjuge_nao_e_meacao():
    riscos = riscos_from_text(
        "Aplica-se a regra do cônjuge do executado. Comunhão universal. "
        "O arrematante e seu cônjuge deverão assinar."
    )
    assert "meacao" not in riscos


def test_leiloeiro_diverge_entre_edital_e_anuncio():
    riscos = riscos_from_text(
        "Leiloeiro público oficial João da Silva.",
        page_text="Leiloeiro: Maria Souza — Zuk Leilões",
    )
    assert riscos["leiloeiro_ok"] is False


def test_calil_no_site_e_no_edital_nao_diverge():
    riscos = riscos_from_text(
        "Leiloeiro público oficial Marcelo Calil, inscrito na Junta Comercial.",
        page_text="Calil Leilões. O leiloeiro não se responsabiliza pela descrição.",
        source="calil",
    )
    assert riscos.get("leiloeiro_ok") is not False


def test_casa_calil_pelo_source_bate_com_edital():
    riscos = riscos_from_text(
        "Hasta pública conduzida por Calil Leilões.",
        page_text="Apartamento em Ribeirão Preto. Lance inicial R$ 200.000,00.",
        source="calil",
    )
    assert riscos["leiloeiro_ok"] is True


def test_disclaimer_do_leiloeiro_nao_vira_nome():
    riscos = riscos_from_text(
        "Leiloeiro público oficial Marcelo Calil.",
        page_text="O leiloeiro não se responsabiliza pela veracidade das informações.",
        source="calil",
    )
    assert riscos.get("leiloeiro_ok") is not False
    assert "responsabiliza" not in (riscos.get("leiloeiro_site") or "").lower()


def test_sem_texto_nao_inventa_citacao():
    riscos = riscos_from_text("Apartamento com 2 dormitórios, vaga de garagem.")
    assert "citacao" not in riscos
    assert "nao_entrar" not in riscos


if __name__ == "__main__":
    test_nao_citado_e_cnj()
    test_cnj_compacto_formata()
    test_citado_regularmente_nao_trava()
    test_citacao_por_edital()
    test_usufruto_na_matricula()
    test_livre_de_usufruto_nao_marca()
    test_meacao_e_conjuge()
    test_conjuge_do_arrematante_nao_e_meacao()
    test_fracao_ideal_do_condominio_nao_e_meacao()
    test_regra_generica_de_conjuge_nao_e_meacao()
    test_leiloeiro_diverge_entre_edital_e_anuncio()
    test_calil_no_site_e_no_edital_nao_diverge()
    test_casa_calil_pelo_source_bate_com_edital()
    test_disclaimer_do_leiloeiro_nao_vira_nome()
    test_sem_texto_nao_inventa_citacao()
    print("ok")
