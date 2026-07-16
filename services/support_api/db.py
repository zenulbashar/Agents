"""Postgres Store backend (production).

Two connection pools:
  - app pool: the RLS-enforced `support_api_app` role; every tenant-scoped
    query runs in a transaction with `support.app_id` / `support.tenant_id`
    GUCs set from the verified token
  - maintenance pool: owner role for schema apply, webhook worker, retention
    sweep, and the operator surface (cross-tenant by design)

Any driver/pool failure surfaces as StoreUnavailable => HTTP 503 (auth and
replay checks fail closed, never soft-pass).
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json
from psycopg_pool import AsyncConnectionPool

from .models import Conversation, Message, Ticket, WebhookDelivery, now_utc
from .store import StoreUnavailable

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _wrap(exc: Exception) -> StoreUnavailable:
    return StoreUnavailable(f"postgres unavailable: {exc.__class__.__name__}")


class PgStore:
    def __init__(self, app_dsn: str, maintenance_dsn: str | None = None) -> None:
        if not app_dsn:
            raise StoreUnavailable("SUPPORT_DATABASE_URL not configured")
        self._app_pool = AsyncConnectionPool(
            app_dsn, min_size=1, max_size=8, open=False, kwargs={"row_factory": dict_row}
        )
        self._maint_pool = AsyncConnectionPool(
            maintenance_dsn or app_dsn, min_size=1, max_size=4, open=False,
            kwargs={"row_factory": dict_row},
        )

    async def open(self) -> None:
        try:
            await self._app_pool.open(wait=True, timeout=30)
            await self._maint_pool.open(wait=True, timeout=30)
        except Exception as exc:
            raise _wrap(exc) from exc

    async def close(self) -> None:
        await self._app_pool.close()
        await self._maint_pool.close()

    async def apply_schema(self) -> None:
        try:
            async with self._maint_pool.connection() as conn:
                await conn.execute(SCHEMA_PATH.read_text())
        except Exception as exc:
            raise _wrap(exc) from exc

    @asynccontextmanager
    async def _tenant(self, app_id: str, tenant_id: str):
        """Connection with the RLS tenancy context set for this transaction."""
        try:
            async with self._app_pool.connection() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "SELECT set_config('support.app_id', %s, true),"
                        "       set_config('support.tenant_id', %s, true)",
                        (app_id, tenant_id),
                    )
                    yield conn
        except StoreUnavailable:
            raise
        except psycopg.errors.UniqueViolation:
            raise
        except Exception as exc:
            raise _wrap(exc) from exc

    @asynccontextmanager
    async def _maint(self):
        try:
            async with self._maint_pool.connection() as conn:
                yield conn
        except Exception as exc:
            raise _wrap(exc) from exc

    # -- auth -----------------------------------------------------------------

    async def consume_jti(self, app_id: str, jti: str) -> bool:
        try:
            async with self._app_pool.connection() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "SELECT set_config('support.app_id', %s, true)", (app_id,)
                    )
                    await conn.execute(
                        "INSERT INTO consumed_jtis (app_id, jti) VALUES (%s, %s)",
                        (app_id, jti),
                    )
            return True
        except psycopg.errors.UniqueViolation:
            return False
        except Exception as exc:
            raise _wrap(exc) from exc

    # -- conversations / messages ----------------------------------------------

    async def create_conversation(self, conv: Conversation) -> Conversation:
        async with self._tenant(conv.app_id, conv.tenant_id) as conn:
            await conn.execute(
                """INSERT INTO support_conversations
                   (id, app_id, tenant_id, subject_id, subject_email, department,
                    status, created_at, last_message_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (conv.id, conv.app_id, conv.tenant_id, conv.subject_id,
                 conv.subject_email, conv.department, conv.status,
                 conv.created_at, conv.last_message_at),
            )
        return conv

    @staticmethod
    def _conv_from_row(row: dict[str, Any]) -> Conversation:
        return Conversation(
            id=row["id"], app_id=row["app_id"], tenant_id=row["tenant_id"],
            subject_id=row["subject_id"], subject_email=row["subject_email"],
            department=row["department"], status=row["status"],
            created_at=row["created_at"], closed_at=row["closed_at"],
            last_message_at=row["last_message_at"],
        )

    async def get_conversation(self, app_id, tenant_id, subject_id, conversation_id):
        async with self._tenant(app_id, tenant_id) as conn:
            cur = await conn.execute(
                "SELECT * FROM support_conversations WHERE id = %s AND subject_id = %s",
                (conversation_id, subject_id),
            )
            row = await cur.fetchone()
        return self._conv_from_row(row) if row else None

    async def set_conversation_status(self, app_id, tenant_id, conversation_id, status):
        async with self._tenant(app_id, tenant_id) as conn:
            await conn.execute(
                """UPDATE support_conversations
                   SET status = %s,
                       closed_at = CASE WHEN %s = 'closed' THEN now() ELSE closed_at END
                   WHERE id = %s""",
                (status, status, conversation_id),
            )

    async def add_message(self, msg: Message) -> Message:
        async with self._tenant(msg.app_id, msg.tenant_id) as conn:
            await conn.execute(
                """INSERT INTO support_messages
                   (id, conversation_id, app_id, tenant_id, sender, body, sources, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (msg.id, msg.conversation_id, msg.app_id, msg.tenant_id,
                 msg.sender, msg.body, Json(msg.sources), msg.created_at),
            )
            await conn.execute(
                "UPDATE support_conversations SET last_message_at = %s WHERE id = %s",
                (msg.created_at, msg.conversation_id),
            )
        return msg

    async def get_messages(self, app_id, tenant_id, conversation_id):
        async with self._tenant(app_id, tenant_id) as conn:
            cur = await conn.execute(
                "SELECT * FROM support_messages WHERE conversation_id = %s ORDER BY created_at, id",
                (conversation_id,),
            )
            rows = await cur.fetchall()
        return [
            Message(
                id=r["id"], conversation_id=r["conversation_id"], app_id=r["app_id"],
                tenant_id=r["tenant_id"], sender=r["sender"], body=r["body"],
                sources=r["sources"] or [], created_at=r["created_at"],
            )
            for r in rows
        ]

    # -- tickets -----------------------------------------------------------------

    async def create_ticket(self, ticket: Ticket) -> Ticket:
        async with self._tenant(ticket.app_id, ticket.tenant_id) as conn:
            await conn.execute(
                """INSERT INTO support_tickets
                   (id, app_id, tenant_id, conversation_id, department, summary,
                    subject, status, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (ticket.id, ticket.app_id, ticket.tenant_id, ticket.conversation_id,
                 ticket.department, ticket.summary, Json(ticket.subject),
                 ticket.status, ticket.created_at),
            )
        return ticket

    @staticmethod
    def _ticket_from_row(row: dict[str, Any]) -> Ticket:
        return Ticket(
            id=row["id"], app_id=row["app_id"], tenant_id=row["tenant_id"],
            conversation_id=row["conversation_id"], department=row["department"],
            summary=row["summary"], subject=row["subject"] or {}, status=row["status"],
            reply=row["reply"], created_at=row["created_at"], replied_at=row["replied_at"],
        )

    async def get_ticket_any_tenant(self, ticket_id: str) -> Ticket | None:
        """Operator surface only — runs on the owner connection by design."""
        async with self._maint() as conn:
            cur = await conn.execute("SELECT * FROM support_tickets WHERE id = %s", (ticket_id,))
            row = await cur.fetchone()
        return self._ticket_from_row(row) if row else None

    async def list_tickets(self, status: str | None = None, limit: int = 50) -> list[Ticket]:
        async with self._maint() as conn:
            if status:
                cur = await conn.execute(
                    "SELECT * FROM support_tickets WHERE status = %s "
                    "ORDER BY created_at DESC LIMIT %s",
                    (status, limit),
                )
            else:
                cur = await conn.execute(
                    "SELECT * FROM support_tickets ORDER BY created_at DESC LIMIT %s", (limit,)
                )
            rows = await cur.fetchall()
        return [self._ticket_from_row(r) for r in rows]

    async def set_ticket_replied(self, ticket_id: str, reply: str) -> Ticket | None:
        async with self._maint() as conn:
            cur = await conn.execute(
                """UPDATE support_tickets
                   SET status = 'replied', reply = %s, replied_at = now()
                   WHERE id = %s RETURNING *""",
                (reply, ticket_id),
            )
            row = await cur.fetchone()
        return self._ticket_from_row(row) if row else None

    # -- feedback -------------------------------------------------------------

    async def upsert_feedback(self, app_id, tenant_id, conversation_id, rating, reason, comment):
        async with self._tenant(app_id, tenant_id) as conn:
            await conn.execute(
                """INSERT INTO support_feedback
                   (conversation_id, app_id, tenant_id, rating, reason, comment)
                   VALUES (%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (conversation_id) DO UPDATE
                   SET rating = EXCLUDED.rating, reason = EXCLUDED.reason,
                       comment = EXCLUDED.comment, updated_at = now()""",
                (conversation_id, app_id, tenant_id, rating, reason, comment),
            )

    # -- budgets -----------------------------------------------------------------

    async def record_usage(self, app_id, tenant_id, conversation_id, tokens):
        async with self._tenant(app_id, tenant_id) as conn:
            await conn.execute(
                """INSERT INTO support_usage (app_id, tenant_id, conversation_id, day, tokens)
                   VALUES (%s,%s,%s, (now() AT TIME ZONE 'utc')::date, %s)
                   ON CONFLICT (app_id, tenant_id, conversation_id, day)
                   DO UPDATE SET tokens = support_usage.tokens + EXCLUDED.tokens""",
                (app_id, tenant_id, conversation_id, tokens),
            )

    async def usage_today(self, app_id, tenant_id):
        async with self._tenant(app_id, tenant_id) as conn:
            cur = await conn.execute(
                """SELECT COALESCE(SUM(tokens), 0) AS total FROM support_usage
                   WHERE day = (now() AT TIME ZONE 'utc')::date""",
            )
            row = await cur.fetchone()
        return int(row["total"])

    async def usage_conversation(self, app_id, tenant_id, conversation_id):
        async with self._tenant(app_id, tenant_id) as conn:
            cur = await conn.execute(
                "SELECT COALESCE(SUM(tokens), 0) AS total FROM support_usage "
                "WHERE conversation_id = %s",
                (conversation_id,),
            )
            row = await cur.fetchone()
        return int(row["total"])

    # -- webhooks ---------------------------------------------------------------

    async def enqueue_webhook(self, delivery: WebhookDelivery) -> None:
        async with self._maint() as conn:
            await conn.execute(
                """INSERT INTO support_webhook_deliveries
                   (id, app_id, event_type, dedupe_key, payload, status,
                    attempts, next_attempt_at, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (dedupe_key) DO NOTHING""",
                (delivery.id, delivery.app_id, delivery.event_type, delivery.dedupe_key,
                 Json(delivery.payload), delivery.status, delivery.attempts,
                 delivery.next_attempt_at, delivery.created_at),
            )

    async def due_webhooks(self, limit: int = 20) -> list[WebhookDelivery]:
        async with self._maint() as conn:
            cur = await conn.execute(
                """SELECT * FROM support_webhook_deliveries
                   WHERE status = 'pending' AND next_attempt_at <= now()
                   ORDER BY next_attempt_at LIMIT %s""",
                (limit,),
            )
            rows = await cur.fetchall()
        return [
            WebhookDelivery(
                id=r["id"], app_id=r["app_id"], event_type=r["event_type"],
                dedupe_key=r["dedupe_key"], payload=r["payload"], status=r["status"],
                attempts=r["attempts"], next_attempt_at=r["next_attempt_at"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    async def mark_webhook(self, delivery_id, status, attempts, next_attempt_at):
        async with self._maint() as conn:
            await conn.execute(
                """UPDATE support_webhook_deliveries
                   SET status = %s, attempts = %s,
                       next_attempt_at = COALESCE(%s, next_attempt_at),
                       delivered_at = CASE WHEN %s = 'delivered' THEN now() ELSE delivered_at END
                   WHERE id = %s""",
                (status, attempts, next_attempt_at, status, delivery_id),
            )

    # -- retention / erasure -----------------------------------------------------

    async def purge_expired(self, retention_days: int, jti_ttl_seconds: int) -> dict[str, int]:
        cutoff = now_utc() - timedelta(days=retention_days)
        jti_cutoff = now_utc() - timedelta(seconds=jti_ttl_seconds)
        async with self._maint() as conn:
            cur = await conn.execute(
                "DELETE FROM support_conversations WHERE last_message_at < %s RETURNING id",
                (cutoff,),
            )
            conversations = len(await cur.fetchall())
            cur = await conn.execute(
                "DELETE FROM consumed_jtis WHERE consumed_at < %s RETURNING jti", (jti_cutoff,)
            )
            jtis = len(await cur.fetchall())
            await conn.execute(
                "DELETE FROM support_webhook_deliveries "
                "WHERE status = 'delivered' AND created_at < now() - interval '7 days'"
            )
        return {"conversations": conversations, "jtis": jtis}

    async def erase_subject(self, app_id, tenant_id, subject_id) -> dict[str, int]:
        """GDPR/CCPA erasure — cascades transcripts, tickets, feedback, usage."""
        async with self._tenant(app_id, tenant_id) as conn:
            await conn.execute(
                """DELETE FROM support_usage WHERE conversation_id IN
                   (SELECT id FROM support_conversations WHERE subject_id = %s)""",
                (subject_id,),
            )
            cur = await conn.execute(
                "DELETE FROM support_tickets WHERE conversation_id IN "
                "(SELECT id FROM support_conversations WHERE subject_id = %s) RETURNING id",
                (subject_id,),
            )
            tickets = len(await cur.fetchall())
            cur = await conn.execute(
                "DELETE FROM support_conversations WHERE subject_id = %s RETURNING id",
                (subject_id,),
            )
            conversations = len(await cur.fetchall())
        return {"conversations": conversations, "tickets": tickets}
