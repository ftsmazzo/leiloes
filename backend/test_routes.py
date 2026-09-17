import asyncio

from fastapi import BackgroundTasks, HTTPException

import app.scrapers.run_all as run_all_module
from app.api import routes


async def _fake_run_all(on_progress=None):
    if on_progress is not None:
        on_progress("calil", {"total_auctions": 1, "total_lots": 2, "by_source": {"calil": {"auctions": 1, "lots": 2}}})
    return {"total_auctions": 1, "total_lots": 2, "by_source": {"calil": {"auctions": 1, "lots": 2}}, "errors": []}


def test_run_scrape_rejects_while_running():
    routes._scrape_running = True
    routes._scrape_last_finished = None
    try:
        try:
            asyncio.run(routes.run_scrape(BackgroundTasks()))
            assert False, "esperava HTTPException 429"
        except HTTPException as exc:
            assert exc.status_code == 429
    finally:
        routes._scrape_running = False


def test_run_scrape_starts_job_and_enforces_cooldown():
    original = run_all_module.run_all
    run_all_module.run_all = _fake_run_all
    routes._scrape_running = False
    routes._scrape_last_finished = None
    routes._scrape_job.update(status="idle", summary=None, error=None, current_source=None)
    try:

        async def scenario():
            bg = BackgroundTasks()
            result = await routes.run_scrape(bg)
            assert result == {"status": "started"}
            assert routes._scrape_job["status"] == "running"
            # roda a task registrada, como o Starlette faria depois da resposta
            await bg()
            assert routes._scrape_job["status"] == "done"
            assert routes._scrape_job["summary"]["total_lots"] == 2
            assert routes._scrape_last_finished is not None

            try:
                await routes.run_scrape(BackgroundTasks())
                assert False, "esperava HTTPException 429 pelo cooldown"
            except HTTPException as exc:
                assert exc.status_code == 429
                assert "Retry-After" in exc.headers

        asyncio.run(scenario())
    finally:
        run_all_module.run_all = original
        routes._scrape_running = False
        routes._scrape_last_finished = None


def test_run_scrape_progress_snapshot_is_independent():
    """run_all reusa o mesmo dict de summary a cada fonte — o status exposto
    não pode "vazar" a fonte seguinte antes do current_source virar."""
    captured: list[dict] = []

    async def fake_run_all_multi(on_progress=None):
        summary = {"total_auctions": 0, "total_lots": 0, "by_source": {}, "errors": []}
        if on_progress is not None:
            summary["by_source"]["calil"] = {"auctions": 1, "lots": 5}
            summary["total_lots"] = 5
            on_progress("calil", summary)
            captured.append(dict(routes._scrape_job["summary"]))
            # muta o MESMO dict antes do scraper seguinte terminar de verdade
            summary["by_source"]["vegas"] = {"auctions": 1, "lots": 9}
            summary["total_lots"] = 14
            on_progress("vegas", summary)
        return summary

    original = run_all_module.run_all
    run_all_module.run_all = fake_run_all_multi
    routes._scrape_running = False
    routes._scrape_last_finished = None
    routes._scrape_job.update(status="idle", summary=None, error=None, current_source=None)
    try:

        async def scenario():
            bg = BackgroundTasks()
            await routes.run_scrape(bg)
            await bg()

        asyncio.run(scenario())
        assert "vegas" not in captured[0]["by_source"], "snapshot vazou a fonte seguinte"
        assert routes._scrape_job["summary"]["by_source"].get("vegas"), "estado final deveria ter as duas fontes"
    finally:
        run_all_module.run_all = original
        routes._scrape_running = False
        routes._scrape_last_finished = None


if __name__ == "__main__":
    test_run_scrape_rejects_while_running()
    test_run_scrape_starts_job_and_enforces_cooldown()
    test_run_scrape_progress_snapshot_is_independent()
    print("ok")
