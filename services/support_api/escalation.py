"""Escalation -> tickets (Contract v1 §4). No live human agents (D5):
anything the agent can't handle becomes a ticket delivered to the operator
via the existing services/telegram channel.

Built-in triggers (no per-app config):
  1. explicit  — "__human__" sentinel from the widget button, or natural
                 language ("talk to a human", ...); the model also catches
                 phrasing the regex misses via its escalate tool
  2. low confidence — the agent cannot ground an answer (tool call)
  3. frustration / repetitive loop — model tool call, plus a deterministic
     same-question-3-turns detector here
"""
from __future__ import annotations

import difflib
import re

from .models import (
    AuthContext,
    Conversation,
    Message,
    Ticket,
    WebhookDelivery,
    new_id,
    now_utc,
)
from .settings import Settings
from .store import Store

HUMAN_SENTINEL = "__human__"

_HUMAN_PATTERNS = re.compile(
    r"(speak|talk|chat)\s+(to|with)\s+(a\s+)?(human|person|agent|someone|representative|rep|operator)"
    r"|human\s+(agent|support|being|please)"
    r"|real\s+(person|human)"
    r"|\b(a|an)\s+actual\s+(human|person)\b",
    re.IGNORECASE,
)

HOLDING_MESSAGE = (
    "One of our representatives will be with you shortly — we've raised "
    "ticket #{ticket_id} and you'll get a reply by email."
)

LOOP_TURNS = 3
_LOOP_SIMILARITY = 0.9


def wants_human(message: str) -> bool:
    text = message.strip()
    return text == HUMAN_SENTINEL or bool(_HUMAN_PATTERNS.search(text))


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", text.lower()).strip()


def is_repetitive_loop(history: list[Message], new_message: str) -> bool:
    """Same question >=3 turns without resolution (trigger 3)."""
    user_bodies = [m.body for m in history if m.sender == "user"]
    recent = [*user_bodies, new_message][-LOOP_TURNS:]
    if len(recent) < LOOP_TURNS:
        return False
    base = _normalise(recent[0])
    if not base:
        return False
    for other in recent[1:]:
        ratio = difflib.SequenceMatcher(None, base, _normalise(other)).ratio()
        if ratio < _LOOP_SIMILARITY:
            return False
    return True


async def open_ticket(
    *,
    store: Store,
    notifier,
    settings: Settings,
    ctx: AuthContext,
    conversation: Conversation,
    reason: str,
    summary: str,
) -> Ticket:
    """Create the ticket, mark the conversation escalated, notify the
    operator on Telegram, and enqueue the ticket.created webhook."""
    ticket = Ticket(
        id=new_id("tick"),
        app_id=ctx.app_id,
        tenant_id=ctx.tenant_id,
        conversation_id=conversation.id,
        department=conversation.department,
        summary=summary,
        subject=ctx.subject.as_dict(),
    )
    await store.create_ticket(ticket)
    await store.set_conversation_status(ctx.app_id, ctx.tenant_id, conversation.id, "escalated")

    deep_link = ""
    if settings.public_base_url:
        deep_link = f"\n{settings.public_base_url.rstrip('/')}/internal/tickets/{ticket.id}"
    await notifier.notify(
        "SUPPORT TICKET ({reason})\n"
        "App: {app} | Tenant: {tenant} | Dept: {dept}\n"
        "From: {who}\n"
        "{summary}{link}".format(
            reason=reason,
            app=ctx.app_id,
            tenant=ctx.tenant_id,
            dept=conversation.department,
            who=f"{ctx.subject.role}:{ctx.subject.id}"
            + (f" <{ctx.subject.email}>" if ctx.subject.email else ""),
            summary=summary,
            link=deep_link,
        )
    )

    await store.enqueue_webhook(
        WebhookDelivery(
            id=new_id("whd"),
            app_id=ctx.app_id,
            event_type="ticket.created",
            dedupe_key=f"{ticket.id}:ticket.created",
            payload={
                "type": "ticket.created",
                "ticket": ticket.webhook_shape(),
                "ts": int(now_utc().timestamp()),
            },
        )
    )
    return ticket


def holding_message(ticket: Ticket) -> str:
    return HOLDING_MESSAGE.format(ticket_id=ticket.id.removeprefix("tick_")[:8])
