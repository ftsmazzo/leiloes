from app.datajud import (
    citacao_from_movimentos,
    consultar_datajud,
    merge_riscos,
    tribunal_alias,
)


def test_tribunal_tjsp_e_trf():
    assert tribunal_alias("0001234-11.2012.8.26.0100") == "tjsp"
    assert tribunal_alias("0001234-11.2012.4.03.6100") == "trf3"
    assert tribunal_alias("curto") is None


def test_movimentos_citacao_cumprida():
    assert citacao_from_movimentos([{"nome": "Citação cumprida"}]) == "citado"


def test_movimentos_citacao_por_edital():
    assert citacao_from_movimentos([{"nome": "Citação por edital"}]) == "edital"


def test_movimentos_citacao_negativa():
    assert citacao_from_movimentos([{"nome": "Citação negativa / infrutífera"}]) == "nao_citado"


def test_movimentos_so_expedicao_fica_pendente():
    assert citacao_from_movimentos([{"nome": "Expedição de mandado de citação"}]) == "pendente"


def test_sem_movimento_de_citacao_nao_inventa():
    assert citacao_from_movimentos([{"nome": "Juntada de petição"}]) is None


def test_consultar_datajud_usa_fetch_injetado():
    def fake(_url, _payload):
        return {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "tribunal": "TJSP",
                            "classe": {"nome": "Execução de Título Extrajudicial"},
                            "dataAjuizamento": "2012-11-22T00:00:00.000Z",
                            "movimentos": [{"nome": "Citação cumprida"}],
                        }
                    }
                ]
            }
        }

    out = consultar_datajud("0001234-11.2012.8.26.0100", fetch=fake)
    assert out["datajud"] == "ok"
    assert out["citacao"] == "citado"
    assert out["citacao_fonte"] == "datajud"
    assert "nao_entrar" not in out


def test_merge_datajud_ganha_na_citacao_e_pdf_fica_com_usufruto():
    base = {"citacao": "nao_citado", "nao_entrar": True, "usufruto": True}
    dj = {"datajud": "ok", "citacao": "citado", "citacao_fonte": "datajud"}
    merged = merge_riscos(base, dj)
    assert merged["citacao"] == "citado"
    assert "nao_entrar" not in merged
    assert merged["usufruto"] is True


def test_merge_sem_evidencia_datajud_mantem_pdf():
    base = {"citacao": "nao_citado", "nao_entrar": True}
    merged = merge_riscos(base, {"datajud": "nao_encontrado"})
    assert merged["citacao"] == "nao_citado"
    assert merged["nao_entrar"] is True


if __name__ == "__main__":
    test_tribunal_tjsp_e_trf()
    test_movimentos_citacao_cumprida()
    test_movimentos_citacao_por_edital()
    test_movimentos_citacao_negativa()
    test_movimentos_so_expedicao_fica_pendente()
    test_sem_movimento_de_citacao_nao_inventa()
    test_consultar_datajud_usa_fetch_injetado()
    test_merge_datajud_ganha_na_citacao_e_pdf_fica_com_usufruto()
    test_merge_sem_evidencia_datajud_mantem_pdf()
    print("ok")
