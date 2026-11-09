from app.gliner_avaliar import fatos_gliner, mesclar_gliner, ocupacao_se_afirmada


def test_caso_esteja_ocupado_nao_e_ocupacao():
    text = "§ 3º: Caso o imóvel esteja ocupado, a desocupação dependerá de mandado."
    assert ocupacao_se_afirmada(text, "ocupado") is None


def test_imovel_ocupado_afirmado_permanece():
    text = "Imóvel ocupado pelo executado."
    assert ocupacao_se_afirmada(text, "ocupado") == "ocupado"


def test_gliner_preenche_cnj_e_area_ausentes():
    def fetch(_text, _labels):
        return {"cnj": ["0000467-17.2025.8.26.0094"], "area": ["100,00 m²"]}

    out = fatos_gliner("Edital de hasta pública do imóvel.", fetch=fetch)
    assert out["processo_cnj"] == "0000467-17.2025.8.26.0094"
    assert "100" in out["area"]
    assert out["extract_avaliar"] == "gliner"


def test_gliner_nao_afirma_ocupacao_hedged():
    def fetch(_text, _labels):
        return {"ocupacao": ["Caso o imóvel esteja ocupado"]}

    out = fatos_gliner(
        "Caso o imóvel esteja ocupado, a desocupação dependerá de mandado.",
        fetch=fetch,
    )
    assert "ocupacao" not in out


def test_gliner_nao_sobrescreve_ocupacao_do_regex():
    dst = {"ocupacao": "desocupado"}
    riscos: dict = {}
    mesclar_gliner(dst, riscos, {"ocupacao": "ocupado", "processo_cnj": "0000467-17.2025.8.26.0094"})
    assert dst["ocupacao"] == "desocupado"
    assert riscos["processo_cnj"] == "0000467-17.2025.8.26.0094"


def test_sem_gliner_configurado_nao_quebra():
    import os

    os.environ.pop("GLINER_URL", None)
    os.environ.pop("GLINER_API_TOKEN", None)
    assert fatos_gliner("Imóvel desocupado.") == {}


if __name__ == "__main__":
    test_caso_esteja_ocupado_nao_e_ocupacao()
    test_imovel_ocupado_afirmado_permanece()
    test_gliner_preenche_cnj_e_area_ausentes()
    test_gliner_nao_afirma_ocupacao_hedged()
    test_gliner_nao_sobrescreve_ocupacao_do_regex()
    test_sem_gliner_configurado_nao_quebra()
    print("ok")
