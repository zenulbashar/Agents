"""Outbound webhooks: Foundry -> client app (Contract v1 §5).

POST {app.webhook_url} with X-Signature: hex(HMAC-SHA256(webhook_secret,
raw_body)); retry with exponential backoff on non-2xx. Deliveries are
durable rows (survive restarts); idempotent by ticket.id + type — the
dedupe key — so receivers can upsert.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import timedelta

import httpx

from .models import now_utc
from .settings import AppRegistry, Settings
from .store import Store

log = logging.getLogger("support_api.webhooks")

_BASE_DELAY_SECONDS = 5
_MAX_DELAY_SECONDS = 3600


def sign(secret: bytes, raw_body: bytes) -> str:
    return hmac.new(secret, raw_body, hashlib.sha256).hexdigest()


def backoff_delay(attempts: int) -> timedelta:
    return timedelta(seconds=min(_BASE_DELAY_SECONDS * (2 ** attempts), _MAX_DELAY_SECONDS))


async def deliver_pending(
    store: Store,
    registry: AppRegistry,
    settings: Settings,
    client: httpx.AsyncClient,
) -> int:
    """One delivery pass over due webhooks. Returns how many were attempted."""
    due = await store.due_webhooks()
    for delivery in due:
        app = registry.get(delivery.app_id)
        if app is None or not app.webhook_url or not app.webhook_secret:
            await store.mark_webhook(delivery.id, "failed", delivery.attempts, None)
            log.warning("webhook %s dropped: app %s has no webhook config",
                        delivery.id, delivery.app_id)
            continue
        raw = json.dumps(delivery.payload, separators=(",", ":")).encode()
        attempts = delivery.attempts + 1
        try:
            resp = await client.post(
                app.webhook_url,
                content=raw,
                headers={
                    "Content-Type": "application/json",
                    "X-Signature": sign(app.webhook_secret, raw),
                },
                timeout=15.0,
            )
            ok = 200 <= resp.status_code < 300
        except httpx.HTTPError as exc:
            log.info("webhook %s attempt %d error: %s", delivery.id, attempts, exc)
            ok = False
        if ok:
            await store.mark_webhook(delivery.id, "delivered", attempts, None)
        elif attempts >= settings.webhook_max_attempts:
            await store.mark_webhook(delivery.id, "failed", attempts, None)
            log.error("webhook %s failed permanently after %d attempts", delivery.id, attempts)
        else:
            await store.mark_webhook(
                delivery.id, "pending", attempts, now_utc() + backoff_delay(attempts)
            )
    return len(due)


async def run_webhook_worker(store: Store, registry: AppRegistry, settings: Settings) -> None:
    """Background loop: poll for due deliveries and send them."""
    async with httpx.AsyncClient() as client:
        while True:
            try:
                await deliver_pending(store, registry, settings, client)
            except Exception:
                log.exception("webhook delivery pass failed")
            await asyncio.sleep(settings.webhook_poll_seconds)
