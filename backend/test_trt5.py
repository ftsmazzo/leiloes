from pathlib import Path

from app.scrapers.registry import source_names
from app.scrapers.trt5 import lots_from_html

ROOT = Path(__file__).resolve().parent
TRT5 = ROOT / "fixtures" / "trt5_leiloes.html"


def test_registry_includes_trt5():
    assert "trt5" in source_names()


def test_trt5_only_keeps_edital_de_alienacao():
    lots = lots_from_html(TRT5.read_text(encoding="utf-8"), "https://www.trt5.jus.br")
    assert len(lots) >= 1
    for lot in lots:
        assert "aliena" in lot.title.lower()
        # nada de "Leilão Unificado" (evento bundled) nem "Instruções"/"Provimento" (docs administrativos)
        assert "unificado" not in lot.title.lower()
        assert "instru" not in lot.title.lower()
        assert "provimento" not in lot.title.lower()


def test_trt5_filters_out_veiculo():
    lots = lots_from_html(TRT5.read_text(encoding="utf-8"), "https://www.trt5.jus.br")
    assert not any("caminh" in lot.title.lower() or "toyota" in lot.title.lower() for lot in lots)
    assert not any(lot.category == "veiculo" for lot in lots)


def test_trt5_extracts_tipo_and_cidade_when_available():
    lots = lots_from_html(TRT5.read_text(encoding="utf-8"), "https://www.trt5.jus.br")
    apto = next(lot for lot in lots if "APTO.1910" in lot.title)
    assert apto.category == "apartamento"
    assert apto.url.endswith(".pdf")

    sala = next(lot for lot in lots if "19.201" in lot.url)
    assert "Salvador" in sala.raw_data


def test_trt5_same_processo_different_apartments_are_distinct_lots():
    lots = lots_from_html(TRT5.read_text(encoding="utf-8"), "https://www.trt5.jus.br")
    ids = {lot.external_id for lot in lots if "0000222-22.2025.5.05.003" in lot.external_id}
    assert len(ids) == 2


if __name__ == "__main__":
    test_registry_includes_trt5()
    test_trt5_only_keeps_edital_de_alienacao()
    test_trt5_filters_out_veiculo()
    test_trt5_extracts_tipo_and_cidade_when_available()
    test_trt5_same_processo_different_apartments_are_distinct_lots()
    print("ok")
