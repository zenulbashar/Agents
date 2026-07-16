"""Storage interface + in-memory backend.

The Postgres backend (db.py) is the production store — tenancy is enforced
there with row-level security. The memory backend exists for tests and
keyless local dev (SUPPORT_STORE=memory); it applies the same scoping in
Python so behaviour matches.

Every tenant-scoped method takes the verified AuthContext-derived
(app_id, tenant_id) explicitly — never values from a request body.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from .models import (
    Conversation,
    Message,
    Ticket,
    WebhookDelivery,
    new_id,
    now_utc,
)


class StoreUnavailable(RuntimeError):
    """Raised when the backing store cannot serve a request (=> HTTP 503)."""


class Store(Protocol):
    # -- auth ---------------------------------------------------------------
    async def consume_jti(self, app_id: str, jti: str) -> bool: ...

    # -- conversations / messages -------------------------------------------
    async def create_conversation(self, conv: Conversation) -> Conversation: ...
    async def get_conversation(
        self, app_id: str, tenant_id: str, subject_id: str, conversation_id: str
    ) -> Conversation | None: ...
    async def set_conversation_status(
        self, app_id: str, tenant_id: str, conversation_id: str, status: str
    ) -> None: ...
    async def add_message(self, msg: Message) -> Message: ...
    async def get_messages(
        self, app_id: str, tenant_id: str, conversation_id: str
    ) -> list[Message]: ...

    # -- tickets --------------------------------------------------------------
    async def create_ticket(self, ticket: Ticket) -> Ticket: ...
    async def get_ticket_any_tenant(self, ticket_id: str) -> Ticket | None: ...
    async def list_tickets(self, status: str | None = None, limit: int = 50) -> list[Ticket]: ...
    async def set_ticket_replied(self, ticket_id: str, reply: str) -> Ticket | None: ...

    # -- feedback -------------------------------------------------------------
    async def upsert_feedback(
        self, app_id: str, tenant_id: str, conversation_id: str,
        rating: str, reason: str | None, comment: str | None,
    ) -> None: ...

    # -- budgets ---------------------------------------------------------------
    async def record_usage(
        self, app_id: str, tenant_id: str, conversation_id: str, tokens: int
    ) -> None: ...
    async def usage_today(self, app_id: str, tenant_id: str) -> int: ...
    async def usage_conversation(
        self, app_id: str, tenant_id: str, conversation_id: str
    ) -> int: ...

    # -- webhooks ----------------------------------------------------------------
    async def enqueue_webhook(self, delivery: WebhookDelivery) -> None: ...
    async def due_webhooks(self, limit: int = 20) -> list[WebhookDelivery]: ...
    async def mark_webhook(
        self, delivery_id: str, status: str, attempts: int, next_attempt_at: datetime | None
    ) -> None: ...

    # -- retention / erasure --------------------------------------------------
    async def purge_expired(self, retention_days: int, jti_ttl_seconds: int) -> dict[str, int]: ...
    async def erase_subject(self, app_id: str, tenant_id: str, subject_id: str) -> dict[str, int]: ...


class MemoryStore:
    """Dict-backed Store used by tests and keyless dev runs."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.jtis: dict[tuple[str, str], datetime] = {}
        self.conversations: dict[str, Conversation] = {}
        self.messages: dict[str, list[Message]] = {}
        self.tickets: dict[str, Ticket] = {}
        self.feedback: dict[str, dict[str, Any]] = {}
        self.usage: list[dict[str, Any]] = []
        self.webhooks: dict[str, WebhookDelivery] = {}

    async def consume_jti(self, app_id: str, jti: str) -> bool:
        async with self._lock:
            key = (app_id, jti)
            if key in self.jtis:
                return False
            self.jtis[key] = now_utc()
            return True

    async def create_conversation(self, conv: Conversation) -> Conversation:
        self.conversations[conv.id] = conv
        self.messages.setdefault(conv.id, [])
        return conv

    def _scoped(self, app_id: str, tenant_id: str, conversation_id: str) -> Conversation | None:
        conv = self.conversations.get(conversation_id)
        if conv and conv.app_id == app_id and conv.tenant_id == tenant_id:
            return conv
        return None

    async def get_conversation(self, app_id, tenant_id, subject_id, conversation_id):
        conv = self._scoped(app_id, tenant_id, conversation_id)
        if conv and conv.subject_id == subject_id:
            return conv
        return None

    async def set_conversation_status(self, app_id, tenant_id, conversation_id, status):
        conv = self._scoped(app_id, tenant_id, conversation_id)
        if conv:
            conv.status = status  # type: ignore[assignment]
            if status == "closed":
                conv.closed_at = now_utc()

    async def add_message(self, msg: Message) -> Message:
        conv = self._scoped(msg.app_id, msg.tenant_id, msg.conversation_id)
        if conv is None:
            raise StoreUnavailable("conversation not found for message")
        self.messages.setdefault(msg.conversation_id, []).append(msg)
        conv.last_message_at = msg.created_at
        return msg

    async def get_messages(self, app_id, tenant_id, conversation_id):
        if self._scoped(app_id, tenant_id, conversation_id) is None:
            return []
        return list(self.messages.get(conversation_id, []))

    async def create_ticket(self, ticket: Ticket) -> Ticket:
        self.tickets[ticket.id] = ticket
        return ticket

    async def get_ticket_any_tenant(self, ticket_id: str) -> Ticket | None:
        return self.tickets.get(ticket_id)

    async def list_tickets(self, status: str | None = None, limit: int = 50) -> list[Ticket]:
        tickets = [t for t in self.tickets.values() if status is None or t.status == status]
        tickets.sort(key=lambda t: t.created_at, reverse=True)
        return tickets[:limit]

    async def set_ticket_replied(self, ticket_id: str, reply: str) -> Ticket | None:
        ticket = self.tickets.get(ticket_id)
        if ticket is None:
            return None
        ticket.status = "replied"
        ticket.reply = reply
        ticket.replied_at = now_utc()
        return ticket

    async def upsert_feedback(self, app_id, tenant_id, conversation_id, rating, reason, comment):
        if self._scoped(app_id, tenant_id, conversation_id) is None:
            raise StoreUnavailable("conversation not found for feedback")
        self.feedback[conversation_id] = {
            "app_id": app_id, "tenant_id": tenant_id, "conversation_id": conversation_id,
            "rating": rating, "reason": reason, "comment": comment, "created_at": now_utc(),
        }

    async def record_usage(self, app_id, tenant_id, conversation_id, tokens):
        self.usage.append({
            "app_id": app_id, "tenant_id": tenant_id, "conversation_id": conversation_id,
            "tokens": tokens, "day": now_utc().date(),
        })

    async def usage_today(self, app_id, tenant_id):
        today = now_utc().date()
        return sum(
            u["tokens"] for u in self.usage
            if u["app_id"] == app_id and u["tenant_id"] == tenant_id and u["day"] == today
        )

    async def usage_conversation(self, app_id, tenant_id, conversation_id):
        return sum(
            u["tokens"] for u in self.usage
            if u["app_id"] == app_id and u["tenant_id"] == tenant_id
            and u["conversation_id"] == conversation_id
        )

    async def enqueue_webhook(self, delivery: WebhookDelivery) -> None:
        for existing in self.webhooks.values():
            if existing.dedupe_key == delivery.dedupe_key:
                return  # idempotent by ticket.id + type
        self.webhooks[delivery.id] = delivery

    async def due_webhooks(self, limit: int = 20) -> list[WebhookDelivery]:
        now = now_utc()
        due = [
            d for d in self.webhooks.values()
            if d.status == "pending" and d.next_attempt_at <= now
        ]
        due.sort(key=lambda d: d.next_attempt_at)
        return due[:limit]

    async def mark_webhook(self, delivery_id, status, attempts, next_attempt_at):
        d = self.webhooks.get(delivery_id)
        if d is None:
            return
        d.status = status
        d.attempts = attempts
        if next_attempt_at is not None:
            d.next_attempt_at = next_attempt_at

    async def purge_expired(self, retention_days: int, jti_ttl_seconds: int) -> dict[str, int]:
        now = now_utc()
        cutoff = now - timedelta(days=retention_days)
        expired = [cid for cid, c in self.conversations.items() if c.last_message_at < cutoff]
        for cid in expired:
            self.conversations.pop(cid, None)
            self.messages.pop(cid, None)
            self.feedback.pop(cid, None)
            for tid in [t for t, tk in self.tickets.items() if tk.conversation_id == cid]:
                self.tickets.pop(tid, None)
        jti_cutoff = now - timedelta(seconds=jti_ttl_seconds)
        stale = [k for k, at in self.jtis.items() if at < jti_cutoff]
        for k in stale:
            self.jtis.pop(k, None)
        return {"conversations": len(expired), "jtis": len(stale)}

    async def erase_subject(self, app_id, tenant_id, subject_id) -> dict[str, int]:
        convs = [
            cid for cid, c in self.conversations.items()
            if c.app_id == app_id and c.tenant_id == tenant_id and c.subject_id == subject_id
        ]
        tickets = 0
        for cid in convs:
            self.conversations.pop(cid, None)
            self.messages.pop(cid, None)
            self.feedback.pop(cid, None)
            for tid in [t for t, tk in self.tickets.items() if tk.conversation_id == cid]:
                self.tickets.pop(tid, None)
                tickets += 1
        return {"conversations": len(convs), "tickets": tickets}


def build_conversation(app_id: str, tenant_id: str, subject_id: str,
                       subject_email: str | None, department: str) -> Conversation:
    return Conversation(
        id=new_id("conv"),
        app_id=app_id,
        tenant_id=tenant_id,
        subject_id=subject_id,
        subject_email=subject_email,
        department=department,
    )
