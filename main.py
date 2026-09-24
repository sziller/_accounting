# main.py

from __future__ import annotations

import app.core.config as conf
import logging

import uvicorn
from fastapi import FastAPI

from fastapi.staticfiles import StaticFiles
from app.routers.router_frontend import FrontendRouter

from app.db.database import create_db_session, init_db
from app.routers.router_accounting_entries import AccountingEntriesRouter
from app.routers.router_receivables import ReceivablesRouter
from app.routers.router_yearly_accounting_summary import YearlyAccountingSummaryRouter
from app.services.mnb_exchange_rate_sync_service import (
    MnbExchangeRateProviderError,
    MnbExchangeRateSyncService,
)

from app.services.ecb_exchange_rate_sync_service import EcbExchangeRateSyncService
from app.services.historical_exchange_rate_service import ExchangeRateProviderError

logger = logging.getLogger(__name__)


def synchronize_ecb_rates_on_startup() -> None:
    """Same session/error lifecycle as MNB; never perform accounting conversion."""
    db = create_db_session()
    try:
        result = EcbExchangeRateSyncService(db=db).synchronize()
        logger.info("ECB EUR/USD synchronization processed %s observations", result.processed_count)
    except ExchangeRateProviderError:
        logger.exception("ECB synchronization failed; locally stored exchange rates may not be current")
    finally:
        db.close()


def synchronize_mnb_rates_on_startup() -> None:
    """Run non-optional MNB dataset synchronization after ``init_db()``.

    This integration point executes on every real application construction,
    including each Uvicorn reload-created server process.  Remote MNB failures
    are logged as non-fatal because local bookkeeping must remain available
    with possibly stale rates.  Local table/schema and database exceptions are
    intentionally not caught and therefore prevent a misleading successful
    startup.  No pending accounting entries are reprocessed here.
    """
    db = create_db_session()
    try:
        MnbExchangeRateSyncService(db=db).synchronize()
    except MnbExchangeRateProviderError:
        logger.exception(
            "MNB synchronization failed; locally stored exchange rates may not be current"
        )
    finally:
        db.close()


def create_app() -> FastAPI:
    """=== main function ====
    Build and configure the local bookkeeping FastAPI application.
    === by Sziller & ChatGPT ==="""
    api = FastAPI(
        title="Local Bookkeeping App",
        version="0.1.0",
    )

    init_db()
    synchronize_mnb_rates_on_startup()
    synchronize_ecb_rates_on_startup()

    api.mount("/static", StaticFiles(directory="app/static"), name="static")
    frontend_router = FrontendRouter()
    api.include_router(frontend_router)

    accounting_router = AccountingEntriesRouter(prefix="/acct",
                                                env_ns="ACCT",
                                                db_roles=["ACCT"])
    accounting_router.reinit()

    api.include_router(accounting_router)
    api.include_router(ReceivablesRouter())
    api.include_router(YearlyAccountingSummaryRouter())

    return api


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=conf.HOST,
        port=conf.PORT,
        reload=True,
    )
