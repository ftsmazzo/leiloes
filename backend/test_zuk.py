from pathlib import Path
import json

from app.scrapers.registry import source_names
from app.scrapers.zuk import lots_from_html

ROOT = Path(__file__).resolve().parent
ZUK = ROOT / "fixtures" / "zuk_imoveis.html"


def test_registry_includes_zuk():
    assert "zuk" in source_names()


def test_zuk_listing_has_city_address_bid():
    lots = lots_from_html(ZUK.read_text(encoding="utf-8"), "https://www.portalzuk.com.br")
    assert len(lots) >= 1
    lot = lots[0]
    assert lot.external_id == "37209-232155"
    assert lot.current_bid == 129585.91
    assert lot.raw_data and "Lorena" in lot.raw_data
    assert "Piauí" in (lot.raw_data or "") or "Piaui" in (lot.raw_data or "")
    assert lot.category == "terreno"
    assert lot.url and "/imovel/" in lot.url
    extra = json.loads(lot.raw_data or "{}")
    pracas = extra.get("pracas") or []
    assert [p["n"] for p in pracas] == [1, 2]
    assert pracas[0]["valor"] == 259171.81
    assert pracas[0]["fim"].startswith("2026-08-28")
    assert pracas[1]["valor"] == 129585.91
    assert pracas[1]["fim"].startswith("2026-09-17")


if __name__ == "__main__":
    test_registry_includes_zuk()
    test_zuk_listing_has_city_address_bid()
    print("ok")
