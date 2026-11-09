from datetime import datetime
from pathlib import Path
import json

from app.scrapers.listing import pracas_from_html
from app.scrapers.soleon import fill_item_details, lots_from_imovel_list, needs_detail, parse_item_detail

ROOT = Path(__file__).resolve().parent


def test_calil_item_grava_datas_e_valores_das_pracas():
    html = (ROOT / "fixtures" / "calil_item.html").read_text(encoding="utf-8")
    lot = parse_item_detail(html, "https://www.calilleiloes.com.br", "1097")
    extra = json.loads(lot.raw_data or "{}")
    pracas = extra.get("pracas") or []
    assert [p["n"] for p in pracas] == [1, 2]
    assert pracas[0]["valor"] == 251136.63
    assert pracas[0]["fim"] == "2026-10-29T14:00:00"
    assert pracas[1]["valor"] == 125568.32
    assert pracas[1]["fim"] == "2026-11-18T14:00:00"
    marked = pracas_from_html(html, now=datetime(2026, 9, 20, 12, 0))
    assert marked[0].get("ativa") is True
    assert extra["processo_cnj"] == "0000467-17.2025.8.26.0094"
    assert extra["ocupacao"] == "desocupado"
    assert "100" in extra["area"]
    assert extra["dividas"]["iptu"] == 3200.0
    assert extra["dividas"]["condominio"] == 12500.0


def test_rotulo_hipotetico_nao_vira_ocupacao():
    from app.scrapers.soleon import fatos_from_html

    html = "<b>Ocupação:</b> Caso o imóvel esteja ocupado, a desocupação dependerá de mandado."
    assert "ocupacao" not in fatos_from_html(html)


def test_calil_listagem_grava_segunda_praca_quando_so_ela_aparece():
    html = (ROOT / "fixtures" / "calil_imovel.html").read_text(encoding="utf-8")
    lots = lots_from_imovel_list(html, "https://www.calilleiloes.com.br")
    extra = json.loads(lots[0].raw_data or "{}")
    pracas = extra.get("pracas") or []
    assert pracas and pracas[0]["n"] == 2
    assert pracas[0]["valor"] == 125568.32


def test_needs_detail_quando_falta_praca_ou_processo():
    listing = (ROOT / "fixtures" / "calil_imovel.html").read_text(encoding="utf-8")
    lots = lots_from_imovel_list(listing, "https://www.calilleiloes.com.br")
    assert needs_detail(lots[0])
    item = parse_item_detail(
        (ROOT / "fixtures" / "calil_item.html").read_text(encoding="utf-8"),
        "https://www.calilleiloes.com.br",
        "1097",
    )
    assert not needs_detail(item)


def test_fill_item_details_completa_card_raso_sem_pdf():
    listing = (ROOT / "fixtures" / "calil_imovel.html").read_text(encoding="utf-8")
    item = (ROOT / "fixtures" / "calil_item.html").read_text(encoding="utf-8")
    lots = lots_from_imovel_list(listing, "https://www.calilleiloes.com.br")
    fetched: list[str] = []

    def fetch_html(url: str) -> str:
        fetched.append(url)
        assert ".pdf" not in url.lower()
        return item

    filled = fill_item_details(
        lots,
        base_url="https://www.calilleiloes.com.br",
        fetch_html=fetch_html,
        cap=1,
    )
    extra = json.loads(filled[0].raw_data or "{}")
    assert [p["n"] for p in extra["pracas"]] == [1, 2]
    assert extra["processo_cnj"] == "0000467-17.2025.8.26.0094"
    assert len(fetched) == 1
    assert needs_detail(filled[1])


if __name__ == "__main__":
    test_calil_item_grava_datas_e_valores_das_pracas()
    test_calil_listagem_grava_segunda_praca_quando_so_ela_aparece()
    test_rotulo_hipotetico_nao_vira_ocupacao()
    test_needs_detail_quando_falta_praca_ou_processo()
    test_fill_item_details_completa_card_raso_sem_pdf()
    print("ok")
