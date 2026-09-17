import asyncio

from fastapi import HTTPException

import app.scrapers.run_all as run_all_module
from app.api import routes


async def _fake_run_all():
    return {"total_auctions": 0, "total_lots": 0, "by_source": {}}


def test_run_scrape_rejects_while_running():
    routes._scrape_running = True
    routes._scrape_last_finished = None
    try:
        try:
            asyncio.run(routes.run_scrape())
            assert False, "esperava HTTPException 429"
        except HTTPException as exc:
            assert exc.status_code == 429
    finally:
        routes._scrape_running = False


def test_run_scrape_enforces_cooldown_between_runs():
    original = run_all_module.run_all
    run_all_module.run_all = _fake_run_all
    routes._scrape_running = False
    routes._scrape_last_finished = None
    try:
        result = asyncio.run(routes.run_scrape())
        assert result["status"] == "ok"
        assert routes._scrape_last_finished is not None

        try:
            asyncio.run(routes.run_scrape())
            assert False, "esperava HTTPException 429 pelo cooldown"
        except HTTPException as exc:
            assert exc.status_code == 429
            assert "Retry-After" in exc.headers
    finally:
        run_all_module.run_all = original
        routes._scrape_running = False
        routes._scrape_last_finished = None


if __name__ == "__main__":
    test_run_scrape_rejects_while_running()
    test_run_scrape_enforces_cooldown_between_runs()
    print("ok")
