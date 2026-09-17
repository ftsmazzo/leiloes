from app.scrapers.extract import cidade_from_text, enrich_extra, format_card, tipo_from_text


def test_tipo_from_title():
    assert tipo_from_text("APARTAMENTO no Mirante") == "apartamento"
    assert tipo_from_text("CASA RESIDENCIAL no Parque") == "casa"
    assert tipo_from_text("Terreno urbano 25000m2") == "terreno"
    assert tipo_from_text("Honda CG 160") == "veiculo"
    assert tipo_from_text("3.400 Fronhas marca Capri") != "sala"


def test_cidade_na_cidade_de():
    assert (
        cidade_from_text("APARTAMENTO na cidade de Ribeirão Preto/SP") == "Ribeirão Preto"
    )


def test_cidade_locality_comma_uf():
    """Campo isolado tipo .card-locality do Zuk/Mega/Grupo Lance: 'Cidade, UF'."""
    assert cidade_from_text("Formiga, MG") == "Formiga"
    assert cidade_from_text("Santa Rosa De Viterbo, SP") == "Santa Rosa De Viterbo"
    # frase com barra não pode ser confundida com o campo isolado
    assert cidade_from_text("Casa em Sertaozinho/SP") == "Sertaozinho"


def test_enrich_regex_without_ai():
    extra = enrich_extra(
        "CASA RESIDENCIAL na cidade de Brodowski/SP",
        "Cidade: Brodowski/SP Endereço: Rua X, 10 Matrícula: 170.289",
        use_ai=False,
    )
    assert extra.get("cidade") == "Brodowski"
    assert extra.get("tipo") == "casa"
    assert extra.get("endereco") and "Rua X" in extra["endereco"]
    assert extra.get("headline") == "Casa · Brodowski"
    assert extra.get("matricula") and "170.289" in extra["matricula"]


def test_format_card_strips_legal_title():
    card = format_card(
        "DIREITOS AQUISITIVOS - APARTAMENTO Und 06 na cidade de Ribeirão Preto/SP",
        "Cidade: Ribeirão Preto/SP Endereço: Rua Stéfano Baruffi, 1127 Matrícula: 170.289",
        {"cidade": "Ribeirão Preto", "tipo": "apartamento"},
    )
    assert card["headline"] == "Apartamento · Ribeirão Preto"
    assert "DIREITOS" not in card["headline"]
    assert "Baruffi" in (card.get("endereco") or "")
    assert card.get("matricula") == "170.289"


def test_format_card_clips_legal_dump():
    card = format_card(
        "Chácara com 9.780m² em Ribeirão Preto/SP",
        "Cidade: Ribeirão Preto/SP Endereço: Rua C, 580 Matrícula: 134.037 - 1º Cartório Descrição: Os prédios situados nesta cidade",
        {
            "cidade": "Ribeirão Preto",
            "tipo": "terreno",
            "endereco": "Matrícula: 1.562 do CRI Descrição: OS IMÓVEIS",
            "matricula": "Matrícula 134.037 - 1º Cartório Descrição: Os prédios situados nesta cidade, com frente para a Rua C " * 4,
        },
    )
    assert card["tipo"] == "chacara"
    assert card["headline"].startswith("Chácara")
    assert card["endereco"] == "Rua C, 580"
    assert "Descrição" not in (card.get("matricula") or "")
    assert len(card.get("matricula") or "") <= 80


if __name__ == "__main__":
    test_tipo_from_title()
    test_cidade_na_cidade_de()
    test_cidade_locality_comma_uf()
    test_enrich_regex_without_ai()
    test_format_card_strips_legal_title()
    test_format_card_clips_legal_dump()
    print("ok")
