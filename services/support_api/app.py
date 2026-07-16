"""FastAPI app factory + background workers (webhook delivery, retention)."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .agent import NullAgent, SupportAgent
from .budgets import SubjectRateLimiter
from .notifier import NullNotifier, TelegramNotifier
from .retention import run_retention_worker
from .routes import router
from .settings import AppRegistry, Settings
from .store import MemoryStore, StoreUnavailable
from .webhooks import run_webhook_worker

log = logging.getLogger("support_api")


def create_app(
    settings: Settings | None = None,
    *,
    store=None,
    agent=None,
    notifier=None,
    registry: AppRegistry | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.registry = registry or AppRegistry.load(settings.apps_config_path)
        app.state.rate_limiter = SubjectRateLimiter(settings.subject_rate_per_minute)

        owns_store = store is None
        if owns_store:
            if settings.store_backend == "memory":
                log.warning("SUPPORT_STORE=memory — dev/tests only, nothing is durable")
                app.state.store = MemoryStore()
            else:
                from .db import PgStore

                pg = PgStore(settings.database_url, settings.maintenance_database_url)
                await pg.open()
                await pg.apply_schema()
                app.state.store = pg
        else:
            app.state.store = store

        app.state.agent = agent if agent is not None else (
            SupportAgent(settings) if settings.anthropic_api_key else NullAgent()
        )
        if not app.state.agent.available:
            log.warning("no ANTHROPIC_API_KEY — every question escalates to a ticket")
        app.state.notifier = notifier if notifier is not None else TelegramNotifier()

        workers: list[asyncio.Task] = []
        if settings.workers_enabled:
            workers = [
                asyncio.create_task(
                    run_webhook_worker(app.state.store, app.state.registry, settings)
                ),
                asyncio.create_task(run_retention_worker(app.state.store, settings)),
            ]
        try:
            yield
        finally:
            for task in workers:
                task.cancel()
            if owns_store and hasattr(app.state.store, "close"):
                await app.state.store.close()

    app = FastAPI(title="Foundry Support API", version="1.0.0", lifespan=lifespan)
    app.include_router(router)

    @app.exception_handler(StoreUnavailable)
    async def store_unavailable(_: Request, exc: StoreUnavailable) -> JSONResponse:
        log.error("store unavailable: %s", exc)
        return JSONResponse(status_code=503, content={"detail": "service unavailable"})

    return app
