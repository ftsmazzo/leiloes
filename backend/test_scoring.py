from datetime import date

from app.scoring import compute_score


def test_score_sem_nenhuma_referencia_de_preco_fica_parcial():
    result = compute_score(title="Casa em Formiga", current_bid=100000)
    assert result["tem_comparacao_preco"] is False
    assert any("sem referência de preço" in m for m in result["motivos"])
    # ainda calcula um score (risco/praça neutros) em vez de travar
    assert 0 <= result["score"] <= 100


def test_score_com_desconto_grande_sobe_e_avisa_fonte():
    result = compute_score(
        title="Apartamento",
        current_bid=100000,
        valor_mercado_estimado=250000,  # 60% abaixo
    )
    assert result["tem_comparacao_preco"] is True
    assert any("abaixo da referência de mercado" in m for m in result["motivos"])
    assert result["score"] > 50


def test_score_lance_acima_da_referencia_penaliza():
    result = compute_score(
        title="Apartamento",
        current_bid=300000,
        valor_mercado_estimado=200000,  # 50% acima
    )
    assert any("acima da referência de mercado" in m for m in result["motivos"])
    assert result["score"] < 50


def test_score_prioriza_mercado_sobre_avaliacao_do_edital():
    result = compute_score(
        title="Apartamento",
        current_bid=100000,
        reference_value=120000,
        valor_mercado_estimado=250000,
    )
    assert any("referência de mercado" in m for m in result["motivos"])
    assert not any("avaliação do edital" in m for m in result["motivos"])


def test_score_fallback_para_avaliacao_do_edital_sem_mercado():
    result = compute_score(title="Apartamento", current_bid=100000, reference_value=150000)
    assert result["tem_comparacao_preco"] is True
    assert any("avaliação do edital" in m for m in result["motivos"])


def test_fator_risco_ocupado_penaliza():
    com_dado = compute_score(title="Casa", description="Imóvel ocupado pelo antigo proprietário")
    sem_dado = compute_score(title="Casa", description="Terreno plano em condomínio fechado")
    assert com_dado["score"] < sem_dado["score"]
    assert any("ocupado" in m for m in com_dado["motivos"])


def test_fator_risco_desocupado_nao_confunde_com_ocupado():
    result = compute_score(title="Casa", description="Imóvel desocupado, pronto para vistoria")
    assert any("desocupado" in m for m in result["motivos"])
    assert not any(m.startswith("ocupado") and "desocupado" not in m for m in result["motivos"])


def test_fator_risco_divida_penaliza():
    result = compute_score(title="Casa", description="Condomínio em atraso, débitos a apurar")
    assert any("dívida" in m or "débito" in m for m in result["motivos"])


def test_fator_praca_avancada_da_bonus():
    praca1 = compute_score(title="Lote em 1ª Praça")
    praca2 = compute_score(title="Lote em 2ª Praça")
    praca3 = compute_score(title="Lote em 3ª Praça")
    assert praca2["score"] > praca1["score"]
    assert praca3["score"] > praca2["score"]
    assert any("2ª praça" in m for m in praca2["motivos"])


def test_divida_pequena_nao_derruba_score():
    pequena = compute_score(
        title="Apartamento",
        current_bid=198235.60,
        reference_value=400000,
        fonte_avaliacao="laudo",
        dividas={"condominio": 185.97},
    )
    grande = compute_score(
        title="Apartamento",
        current_bid=198235.60,
        reference_value=400000,
        fonte_avaliacao="laudo",
        dividas={"condominio": 80000},
    )
    assert pequena["score"] > grande["score"]
    assert any("impacto baixo" in m for m in pequena["motivos"])


def test_iptu_nao_penaliza_condominio_pesa():
    iptu = compute_score(
        title="Casa em rua",
        current_bid=200000,
        reference_value=400000,
        fonte_avaliacao="laudo",
        dividas={"iptu": 80000},
        tem_divida=False,
    )
    condo = compute_score(
        title="Apartamento",
        current_bid=200000,
        reference_value=400000,
        fonte_avaliacao="laudo",
        dividas={"condominio": 80000},
    )
    assert iptu["score"] > condo["score"]
    assert any("abatido" in m for m in iptu["motivos"])
    assert any("não se abate" in m for m in condo["motivos"])


def test_lance_atual_acima_do_inicial_nao_penaliza():
    so_inicial = compute_score(
        title="Casa em rua",
        current_bid=100000,
        minimum_bid=100000,
        reference_value=400000,
        fonte_avaliacao="laudo",
        tem_divida=False,
    )
    com_concorrencia = compute_score(
        title="Casa em rua",
        current_bid=180000,
        minimum_bid=100000,
        reference_value=400000,
        fonte_avaliacao="laudo",
        tem_divida=False,
    )
    assert com_concorrencia["score"] >= so_inicial["score"]
    assert any("concorrência" in m for m in com_concorrencia["motivos"])
    assert any("pelo lance inicial" in m for m in com_concorrencia["motivos"])
    assert any("lance atual" in m and "avaliação" in m for m in com_concorrencia["motivos"])


def test_alerta_quando_lance_atual_supera_avaliacao():
    result = compute_score(
        title="Casa em rua",
        current_bid=420000,
        minimum_bid=100000,
        reference_value=400000,
        fonte_avaliacao="laudo",
        tem_divida=False,
    )
    assert any("acima da avaliação" in m for m in result["motivos"])
    assert any("concorrência" in m for m in result["motivos"])
    assert result["score"] > 50


def test_venal_nao_penaliza_lance_acima_do_iptu():
    venal = compute_score(
        title="Apartamento",
        current_bid=198235.60,
        reference_value=99755.95,
        fonte_avaliacao="venal_imovel",
    )
    laudo_caro = compute_score(
        title="Apartamento",
        current_bid=198235.60,
        reference_value=99755.95,
        fonte_avaliacao="laudo",
    )
    assert venal["tem_comparacao_preco"] is False
    assert laudo_caro["tem_comparacao_preco"] is True
    assert venal["score"] > laudo_caro["score"]
    assert any("venal" in m.lower() for m in venal["motivos"])


def test_laudo_mais_antigo_sobe_score():
    hoje = date(2026, 9, 17)
    kwargs = dict(
        title="Apartamento",
        current_bid=200000,
        reference_value=400000,
        fonte_avaliacao="laudo",
        hoje=hoje,
    )
    recente = compute_score(avaliacao_data="2025-09-17", **kwargs)
    cinco = compute_score(avaliacao_data="2021-09-17", **kwargs)
    dez = compute_score(avaliacao_data="2016-09-17", **kwargs)
    assert recente["score"] < cinco["score"] < dez["score"]
    assert any("1 ano" in m for m in recente["motivos"])
    assert any("5 anos" in m for m in cinco["motivos"])
    assert any("10 anos" in m and "forte oportunidade" in m for m in dez["motivos"])


def test_nao_citado_limita_score_ao_fundo():
    result = compute_score(
        title="Apartamento",
        current_bid=100000,
        reference_value=400000,
        ocupacao="desocupado",
        riscos={"citacao": "nao_citado", "nao_entrar": True},
    )
    assert result["score"] <= 12
    assert any("não citado" in m for m in result["motivos"])
    assert result["motivos"][0].startswith("executado não citado") or any(
        "não entrar" in m for m in result["motivos"][:2]
    )


def test_usufruto_e_meacao_limitam_score():
    usufruto = compute_score(
        title="Casa",
        current_bid=100000,
        reference_value=400000,
        riscos={"usufruto": True},
    )
    meacao = compute_score(
        title="Casa",
        current_bid=100000,
        reference_value=400000,
        riscos={"meacao": True},
    )
    assert usufruto["score"] <= 28
    assert meacao["score"] <= 28
    assert any("usufruto" in m for m in usufruto["motivos"])
    assert any("meação" in m.lower() or "cônjuge" in m for m in meacao["motivos"])


def test_citado_nao_aplica_teto():
    result = compute_score(
        title="Apartamento",
        current_bid=100000,
        reference_value=400000,
        ocupacao="desocupado",
        riscos={"citacao": "citado", "citacao_fonte": "datajud"},
    )
    assert result["score"] > 12
    assert any("citado (DataJud)" in m for m in result["motivos"])


if __name__ == "__main__":
    test_score_sem_nenhuma_referencia_de_preco_fica_parcial()
    test_score_com_desconto_grande_sobe_e_avisa_fonte()
    test_score_lance_acima_da_referencia_penaliza()
    test_score_prioriza_mercado_sobre_avaliacao_do_edital()
    test_score_fallback_para_avaliacao_do_edital_sem_mercado()
    test_fator_risco_ocupado_penaliza()
    test_fator_risco_desocupado_nao_confunde_com_ocupado()
    test_fator_risco_divida_penaliza()
    test_fator_praca_avancada_da_bonus()
    test_divida_pequena_nao_derruba_score()
    test_iptu_nao_penaliza_condominio_pesa()
    test_lance_atual_acima_do_inicial_nao_penaliza()
    test_alerta_quando_lance_atual_supera_avaliacao()
    test_venal_nao_penaliza_lance_acima_do_iptu()
    test_laudo_mais_antigo_sobe_score()
    test_nao_citado_limita_score_ao_fundo()
    test_usufruto_e_meacao_limitam_score()
    test_citado_nao_aplica_teto()
    print("ok")
