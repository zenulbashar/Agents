"""Retention sweep + GDPR/CCPA erasure (Contract v1 §7).

Foundry is where transcripts live, so erasure must cascade here. The sweep
purges conversations idle past the retention window (default 90 days,
cascading messages/tickets/feedback) and GCs consumed jtis (~10 min TTL).
Runs as an in-process background loop; also invocable as a one-shot job:

    python3 -m services.support_api.retention
"""
from __future__ import annotations

import asyncio
import logging

from .settings import Settings
from .store import Store

log = logging.getLogger("support_api.retention")


async def sweep_once(store: Store, settings: Settings) -> dict[str, int]:
    purged = await store.purge_expired(settings.retention_days, settings.jti_ttl_seconds)
    if purged.get("conversations"):
        log.info("retention sweep purged %s", purged)
    return purged


async def run_retention_worker(store: Store, settings: Settings) -> None:
    while True:
        try:
            await sweep_once(store, settings)
        except Exception:
            log.exception("retention sweep failed")
        await asyncio.sleep(settings.retention_interval_seconds)


def main() -> None:
    from .db import PgStore

    logging.basicConfig(level=logging.INFO)
    settings = Settings.from_env()

    async def _run() -> None:
        store = PgStore(settings.database_url, settings.maintenance_database_url)
        await store.open()
        try:
            result = await sweep_once(store, settings)
            print(f"retention sweep: {result}")
        finally:
            await store.close()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
