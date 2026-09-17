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


def _auction(bid: float, title: str = "Casa em Sertãozinho/SP") -> ScrapedAuction:
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
                raw_data='{"cidade": "Sertãozinho"}',
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


if __name__ == "__main__":
    test_rescrape_updates_bid_and_title_without_duplicate()
    test_none_bid_does_not_wipe_previous()
    print("ok")
