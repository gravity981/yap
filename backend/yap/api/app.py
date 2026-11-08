"""FastAPI application (section 2.1).

uvicorn --factory yap.api.app:create_app_from_env
"""

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from yap.api import errors
from yap.api.routers import (
    admin,
    ai_reviewers,
    auth,
    catalog,
    meta,
    policies,
    portfolios,
    price_providers,
    price_sources,
    rebalances,
    reviews,
    timeline,
)
from yap.api.settings import Settings
from yap.db.engine import make_engine, make_session_factory
from yap.db.migrate import upgrade
from yap.llm.base import AdapterFactory, adapter_for
from yap.prices import AdapterFactory as PriceAdapterFactory
from yap.prices import adapter_for as price_adapter_for
from yap.services import price_update
from yap.services import reviews as reviews_service
from yap.services.common import Clock, SystemClock
from yap.services.secrets import KeyBox
from yap.version import version_info

API_PREFIX = "/api"
SCHEDULER_CHECK_SECONDS = 60
log = logging.getLogger(__name__)


def scheduled_price_update(app: FastAPI) -> None:
    """PRC-07: runs the price update when it is due, also a run missed while the app was
    down (spec 2.5)."""
    with app.state.session_factory() as session:
        if price_update.due(session, app.state.clock):
            price_update.run_update(
                session, app.state.clock, app.state.keys, app.state.price_adapters, "schedule"
            )


async def _price_scheduler(app: FastAPI) -> None:
    while True:
        try:
            await asyncio.to_thread(scheduled_price_update, app)
        except Exception:
            log.exception("Scheduled price update failed")
        await asyncio.sleep(SCHEDULER_CHECK_SECONDS)


def create_app(
    settings: Settings,
    clock: Clock | None = None,
    adapters: AdapterFactory | None = None,
    price_adapters: PriceAdapterFactory | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.migrate_on_startup:
            upgrade(settings.database_url)  # NFR-09
        with app.state.session_factory() as session:
            # Reviews interrupted by a restart are failed and can be started again (2.5)
            if reviews_service.fail_interrupted(session, app.state.clock):
                session.commit()
        scheduler = asyncio.create_task(_price_scheduler(app)) if settings.price_scheduler else None
        yield
        if scheduler is not None:
            scheduler.cancel()
        engine.dispose()

    engine = make_engine(settings.database_url)
    app = FastAPI(
        title="YAP",
        version=version_info().version,
        lifespan=lifespan,
        docs_url=f"{API_PREFIX}/docs" if settings.app_env == "dev" else None,
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json",
    )
    app.state.session_factory = make_session_factory(engine)
    app.state.clock = clock or SystemClock()
    app.state.settings = settings
    app.state.keys = KeyBox(settings.secret_key)
    app.state.adapters = adapters or adapter_for
    app.state.price_adapters = price_adapters or price_adapter_for
    errors.register(app)
    for router in (
        meta.router,
        auth.router,
        admin.router,
        admin.reviewers_router,
        price_providers.router,
        price_providers.update_router,
        price_sources.router,
        ai_reviewers.router,
        catalog.router,
        policies.router,
        policies.versions_router,
        portfolios.router,
        rebalances.router,
        reviews.router,
        timeline.router,
    ):
        app.include_router(router, prefix=API_PREFIX)
    if settings.static_dir:
        _serve_frontend(app, Path(settings.static_dir))
    return app


def _serve_frontend(app: FastAPI, directory: Path) -> None:
    """Static files of the built frontend; every other non-API path gets index.html,
    so the frontend's own routes work on reload."""
    index = directory / "index.html"
    app.mount("/assets", StaticFiles(directory=directory / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = (directory / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(directory.resolve()):
            return FileResponse(candidate)
        return FileResponse(index)


def configure_logging() -> None:
    """Gives the app's loggers uvicorn's format ("WARNING:  ..."); uvicorn only configures
    its own loggers, without this the messages are printed bare."""
    from uvicorn.logging import DefaultFormatter

    app_log = logging.getLogger("yap")
    if app_log.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(DefaultFormatter("%(levelprefix)s %(message)s"))
    app_log.addHandler(handler)
    app_log.setLevel(logging.INFO)


def create_app_from_env() -> FastAPI:
    configure_logging()
    settings = Settings.from_env()
    adapters: AdapterFactory | None = None
    if os.environ.get("LLM_FAKE") == "1":
        # End-to-end tests only: reviews get fixed answers instead of calling a provider
        if settings.app_env == "prod":
            raise RuntimeError("LLM_FAKE must not be set in production")
        from yap.llm.fake import FakeAdapter

        adapters = FakeAdapter
    price_adapters: PriceAdapterFactory | None = None
    if os.environ.get("PRICE_FAKE") == "1":
        # End-to-end tests only: fixed listings and prices instead of the providers
        if settings.app_env == "prod":
            raise RuntimeError("PRICE_FAKE must not be set in production")
        from yap.prices.fake import fake_adapter

        price_adapters = fake_adapter
    return create_app(settings, adapters=adapters, price_adapters=price_adapters)
