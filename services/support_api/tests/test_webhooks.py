"""§5: signed outbound webhooks, retry with backoff, idempotent deliveries."""
from __future__ import annotations

import hashlib
import hmac
import json

import httpx

from services.support_api.models import WebhookDelivery, new_id, now_utc
from services.support_api.store import MemoryStore
from services.support_api.webhooks import backoff_delay, deliver_pending, sign

from conftest import WEBHOOK_SECRET


def _delivery(dedupe_suffix: str = "1") -> WebhookDelivery:
    return WebhookDelivery(
        id=new_id("whd"),
        app_id="prompt2eat",
        event_type="ticket.created",
        dedupe_key=f"tick_1:ticket.created:{dedupe_suffix}",
        payload={
            "type": "ticket.created",
            "ticket": {"id": "tick_1", "conversationId": "conv_1",
                       "tenantId": "venue_abc123", "department": "tech",
                       "summary": "help", "status": "open"},
            "ts": int(now_utc().timestamp()),
        },
    )


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_delivery_signed_and_marked_delivered(registry, settings):
    store = MemoryStore()
    await store.enqueue_webhook(_delivery())
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    async with _client(handler) as client:
        await deliver_pending(store, registry, settings, client)

    assert len(seen) == 1
    request = seen[0]
    assert str(request.url) == "https://client.example/api/support/webhook"
    raw = request.read()
    expected = hmac.new(WEBHOOK_SECRET, raw, hashlib.sha256).hexdigest()
    assert request.headers["X-Signature"] == expected
    payload = json.loads(raw)
    assert payload["type"] == "ticket.created"
    assert payload["ticket"]["tenantId"] == "venue_abc123"
    assert all(d.status == "delivered" for d in store.webhooks.values())


async def test_non_2xx_retries_with_backoff(registry, settings):
    store = MemoryStore()
    await store.enqueue_webhook(_delivery())

    async with _client(lambda req: httpx.Response(500)) as client:
        await deliver_pending(store, registry, settings, client)

    (delivery,) = store.webhooks.values()
    assert delivery.status == "pending"
    assert delivery.attempts == 1
    assert delivery.next_attempt_at > now_utc()  # backed off, not hot-looping

    # Not retried while the backoff window is open.
    calls = []

    async with _client(lambda req: calls.append(1) or httpx.Response(200)) as client:
        await deliver_pending(store, registry, settings, client)
    assert calls == []


async def test_gives_up_after_max_attempts(registry, settings):
    settings.webhook_max_attempts = 3
    store = MemoryStore()
    await store.enqueue_webhook(_delivery())

    async with _client(lambda req: httpx.Response(500)) as client:
        for _ in range(5):
            (delivery,) = store.webhooks.values()
            delivery.next_attempt_at = now_utc()  # force the window open
            await deliver_pending(store, registry, settings, client)

    (delivery,) = store.webhooks.values()
    assert delivery.status == "failed"
    assert delivery.attempts == 3


async def test_connection_error_counts_as_attempt(registry, settings):
    store = MemoryStore()
    await store.enqueue_webhook(_delivery())

    def handler(request: httpx.Request):
        raise httpx.ConnectError("refused")

    async with _client(handler) as client:
        await deliver_pending(store, registry, settings, client)
    (delivery,) = store.webhooks.values()
    assert delivery.status == "pending" and delivery.attempts == 1


async def test_enqueue_is_idempotent_by_dedupe_key():
    store = MemoryStore()
    await store.enqueue_webhook(_delivery("same"))
    await store.enqueue_webhook(_delivery("same"))
    assert len(store.webhooks) == 1


def test_backoff_is_exponential_and_capped():
    assert backoff_delay(1).total_seconds() == 10
    assert backoff_delay(2).total_seconds() == 20
    assert backoff_delay(20).total_seconds() == 3600
