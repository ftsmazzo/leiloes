from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.database import Base
from app.models.schemas import AuctionModel, LotModel
from app.scrapers.base import ScrapedAuction, ScrapedLot
from app.scrapers.persist import persist_auctions


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _auction(bid: float, title: str = "Casa em Sertãozinho/SP", raw_data: str = '{"cidade": "Sertãozinho"}') -> ScrapedAuction:
    return ScrapedAuction(
        external_id="calil-superbid-818",
        source="calil",
        title="Calil Leilões",
        url="https://example.test/calil",
        lots=[
            ScrapedLot(
                external_id="818001",
                title=title,
                current_bid=bid,
                minimum_bid=bid,
                reference_value=320000,
                url="https://example.test/oferta/818001",
                raw_data=raw_data,
            )
        ],
    )


def test_rescrape_updates_bid_and_title_without_duplicate():
    session = _session()
    persist_auctions(session, [_auction(100000, "Casa antiga")])
    session.commit()
    persist_auctions(session, [_auction(150000, "Casa atualizada")])
    session.commit()

    lots = session.execute(select(LotModel)).scalars().all()
    assert len(lots) == 1
    assert lots[0].current_bid == 150000
    assert lots[0].minimum_bid == 150000
    assert lots[0].title == "Casa atualizada"
    assert lots[0].reference_value == 320000

    auctions = session.execute(select(AuctionModel)).scalars().all()
    assert len(auctions) == 1


def test_none_bid_does_not_wipe_previous():
    session = _session()
    persist_auctions(session, [_auction(100000)])
    session.commit()
    stale = ScrapedAuction(
        external_id="calil-superbid-818",
        source="calil",
        title="Calil Leilões",
        lots=[
            ScrapedLot(
                external_id="818001",
                title="Casa em Sertãozinho/SP",
                current_bid=None,
                minimum_bid=None,
                reference_value=None,
                url=None,
                raw_data=None,
                description=None,
                category=None,
            )
        ],
    )
    persist_auctions(session, [stale])
    session.commit()
    lot = session.execute(select(LotModel)).scalar_one()
    assert lot.current_bid == 100000
    assert lot.minimum_bid == 100000
    assert lot.reference_value == 320000
    assert lot.url == "https://example.test/oferta/818001"
    assert lot.raw_data and "Sertãozinho" in lot.raw_data


def test_parecer_and_avaliado_survive_rescrape():
    session = _session()
    persist_auctions(
        session,
        [
            _auction(
                100000,
                "Casa antiga",
                raw_data='{"score": 83, "avaliado_em": "2026-09-17T20:00:00Z", "parecer": "Score 83/100.", "avaliacao_edital": 400000}',
            )
        ],
    )
    session.commit()
    persist_auctions(session, [_auction(110000, "Casa atualizada", raw_data='{"score": 50, "cidade": "Sertãozinho"}')])
    session.commit()
    lot = session.execute(select(LotModel)).scalar_one()
    assert "parecer" in (lot.raw_data or "")
    assert "avaliado_em" in (lot.raw_data or "")
    assert "400000" in (lot.raw_data or "")
    assert lot.current_bid == 110000


def test_alertado_flag_survives_rescrape():
    session = _session()
    persist_auctions(session, [_auction(100000, "Casa antiga", raw_data='{"score": 80, "alertado": true}')])
    session.commit()
    persist_auctions(session, [_auction(90000, "Casa atualizada", raw_data='{"score": 85}')])
    session.commit()

    lot = session.execute(select(LotModel)).scalar_one()
    assert '"alertado": true' in lot.raw_data
    assert '"score": 85' in lot.raw_data


def test_persist_auctions_returns_touched_lots_with_source():
    session = _session()
    touched = persist_auctions(session, [_auction(100000)])
    session.commit()
    assert len(touched) == 1
    lot, source = touched[0]
    assert source == "calil"
    assert lot.external_id == "818001"


if __name__ == "__main__":
    test_rescrape_updates_bid_and_title_without_duplicate()
    test_none_bid_does_not_wipe_previous()
    test_parecer_and_avaliado_survive_rescrape()
    test_alertado_flag_survives_rescrape()
    test_persist_auctions_returns_touched_lots_with_source()
    print("ok")
