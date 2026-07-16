"""HTTP surface (Contract v1 §3, §4, §8 + operator/internal endpoints).

Everything under /v1/* requires both auth layers (§2). All pre-checks (auth,
validation, tenancy, budgets, rate limit) happen BEFORE the stream starts so
they can return proper status codes; anything that fails mid-stream becomes
an {"type":"error"} event followed by [DONE].
"""
from __future__ import annotations

import hashlib
import hmac as hmac_mod
import logging
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from . import agent as agent_mod
from . import escalation, sse
from .auth import AuthError, authenticate
from .budgets import BudgetExceeded, RateLimited, check_budgets
from .kb import load_kb
from .models import (
    AuthContext,
    ChatRequest,
    Conversation,
    ErasureRequest,
    FeedbackRequest,
    Message,
    OperatorReplyRequest,
    Ticket,
    WebhookDelivery,
    new_id,
    now_utc,
)
from .store import build_conversation

log = logging.getLogger("support_api")

router = APIRouter()


async def _authenticated(request: Request) -> tuple[AuthContext, bytes]:
    raw = await request.body()
    try:
        ctx = await authenticate(
            authorization=request.headers.get("authorization"),
            signature=request.headers.get("x-signature"),
            raw_body=raw,
            registry=request.app.state.registry,
            store=request.app.state.store,
        )
    except AuthError as exc:
        log.info("auth rejected: %s", exc.reason)
        raise HTTPException(status_code=401, detail="unauthorized") from exc
    return ctx, raw


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


# ---------------------------------------------------------------------------
# POST /v1/chat  (§3)
# ---------------------------------------------------------------------------

@router.post("/v1/chat")
async def chat(request: Request) -> StreamingResponse:
    state = request.app.state
    ctx, raw = await _authenticated(request)
    try:
        body = ChatRequest.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="invalid request body") from exc

    app_cfg = state.registry.get(ctx.app_id)
    if body.department not in app_cfg.departments:
        raise HTTPException(status_code=422, detail="unknown department")

    try:
        state.rate_limiter.check(ctx)
    except RateLimited:
        raise HTTPException(status_code=429, detail="rate limited")

    is_new = body.conversationId is None
    if is_new:
        conversation = build_conversation(
            ctx.app_id, ctx.tenant_id, ctx.subject.id, ctx.subject.email, body.department
        )
    else:
        # Must belong to (app_id, tenant_id, subject.id) — anything else is a
        # plain 404, so existence never leaks across tenants or subjects.
        conversation = await state.store.get_conversation(
            ctx.app_id, ctx.tenant_id, ctx.subject.id, body.conversationId
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="conversation not found")

    try:
        await check_budgets(state.store, state.settings, ctx, body.conversationId)
    except BudgetExceeded as exc:
        raise HTTPException(status_code=429, detail=f"budget exceeded: {exc.scope}")

    if is_new:
        await state.store.create_conversation(conversation)
    history = await state.store.get_messages(ctx.app_id, ctx.tenant_id, conversation.id)
    user_msg = Message(
        id=new_id("msg"),
        conversation_id=conversation.id,
        app_id=ctx.app_id,
        tenant_id=ctx.tenant_id,
        sender="user",
        body=body.message,
    )
    await state.store.add_message(user_msg)

    return StreamingResponse(
        _chat_stream(state, ctx, conversation, is_new, history, body),
        headers=dict(sse.STREAM_HEADERS),
        media_type="text/event-stream",
    )


async def _chat_stream(
    state: Any,
    ctx: AuthContext,
    conversation: Conversation,
    is_new: bool,
    prior_history: list[Message],
    body: ChatRequest,
) -> AsyncIterator[str]:
    message_id = new_id("msg")
    text_id = new_id("txt")
    reply_parts: list[str] = []
    sources: list[dict[str, Any]] = []
    tokens_used = 0
    ticket: Ticket | None = None

    yield sse.start(message_id)
    if is_new:
        # First event of a new conversation so the client can store the id.
        yield sse.data_part("meta", {"conversationId": conversation.id})
    yield sse.text_start(text_id)

    try:
        # Trigger 1 (explicit) and the deterministic half of trigger 3 (loop)
        # never need the model.
        pending_escalation: tuple[str, str] | None = None
        if escalation.wants_human(body.message):
            pending_escalation = (
                "human_requested",
                "User explicitly asked for a human. Last message: "
                + (body.message if body.message != escalation.HUMAN_SENTINEL
                   else "(widget 'talk to a human' button)"),
            )
        elif escalation.is_repetitive_loop(prior_history, body.message):
            pending_escalation = (
                "loop",
                f"User repeated the same question {escalation.LOOP_TURNS}+ turns without "
                f"resolution: {body.message[:300]}",
            )

        if pending_escalation is None:
            if await state.agent.prescreen(body.message):
                for chunk in _chunks(agent_mod.REFUSAL_TEXT):
                    yield sse.text_delta(text_id, chunk)
                reply_parts.append(agent_mod.REFUSAL_TEXT)
            else:
                app_cfg = state.registry.get(ctx.app_id)
                kb_docs = load_kb(app_cfg.kb_dir, conversation.department)
                history = [*prior_history, Message(
                    id="pending", conversation_id=conversation.id, app_id=ctx.app_id,
                    tenant_id=ctx.tenant_id, sender="user", body=body.message,
                )]
                async for event in state.agent.stream_reply(
                    history=history,
                    kb_docs=kb_docs,
                    department=conversation.department,
                    locale=body.locale,
                ):
                    if isinstance(event, agent_mod.TextDelta):
                        reply_parts.append(event.text)
                        yield sse.text_delta(text_id, event.text)
                    elif isinstance(event, agent_mod.Sources):
                        sources = event.refs
                    elif isinstance(event, agent_mod.Escalate):
                        pending_escalation = (event.reason, event.summary)
                    elif isinstance(event, agent_mod.Usage):
                        tokens_used = event.tokens
        else:
            ack = "Of course — let me get a person to help you with this.\n\n"
            reply_parts.append(ack)
            yield sse.text_delta(text_id, ack)

        if pending_escalation is not None:
            reason, summary = pending_escalation
            ticket = await escalation.open_ticket(
                store=state.store,
                notifier=state.notifier,
                settings=state.settings,
                ctx=ctx,
                conversation=conversation,
                reason=reason,
                summary=summary,
            )
            holding = escalation.holding_message(ticket)
            if reply_parts and not reply_parts[-1].endswith("\n"):
                holding = "\n\n" + holding
            reply_parts.append(holding)
            for chunk in _chunks(holding):
                yield sse.text_delta(text_id, chunk)

        yield sse.text_end(text_id)
        if sources:
            yield sse.data_part("sources", sources)
        if ticket is not None:
            yield sse.data_part(
                "escalation", {"ticketId": ticket.id, "summary": ticket.summary}
            )

        await state.store.add_message(Message(
            id=message_id,
            conversation_id=conversation.id,
            app_id=ctx.app_id,
            tenant_id=ctx.tenant_id,
            sender="assistant",
            body="".join(reply_parts),
            sources=sources,
        ))
        if tokens_used:
            await state.store.record_usage(
                ctx.app_id, ctx.tenant_id, conversation.id, tokens_used
            )

        yield sse.finish()
    except Exception:
        log.exception("chat stream failed (conversation %s)", conversation.id)
        yield sse.error("The assistant hit a problem — please try again.")
    yield sse.DONE


def _chunks(text: str, size: int = 48) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]


# ---------------------------------------------------------------------------
# GET /v1/conversations/{id}  (§8) — widget reopen/resume
# ---------------------------------------------------------------------------

@router.get("/v1/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, request: Request) -> JSONResponse:
    state = request.app.state
    ctx, _ = await _authenticated(request)
    conversation = await state.store.get_conversation(
        ctx.app_id, ctx.tenant_id, ctx.subject.id, conversation_id
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    messages = await state.store.get_messages(ctx.app_id, ctx.tenant_id, conversation_id)
    return JSONResponse({
        "conversation": {
            "id": conversation.id,
            "department": conversation.department,
            "status": conversation.status,
            "createdAt": _iso(conversation.created_at),
            "closedAt": _iso(conversation.closed_at),
            "lastMessageAt": _iso(conversation.last_message_at),
        },
        "messages": [
            {
                "id": m.id,
                "sender": m.sender,
                "body": m.body,
                "sources": m.sources,
                "createdAt": _iso(m.created_at),
            }
            for m in messages
        ],
    })


# ---------------------------------------------------------------------------
# POST /v1/feedback  (§8) — one per conversation; bad => recovery ticket
# ---------------------------------------------------------------------------

@router.post("/v1/feedback")
async def feedback(request: Request) -> JSONResponse:
    state = request.app.state
    ctx, raw = await _authenticated(request)
    try:
        body = FeedbackRequest.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="invalid request body") from exc

    conversation = await state.store.get_conversation(
        ctx.app_id, ctx.tenant_id, ctx.subject.id, body.conversationId
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")

    await state.store.upsert_feedback(
        ctx.app_id, ctx.tenant_id, conversation.id,
        str(body.rating), body.reason, body.comment,
    )

    ticket_id: str | None = None
    if body.is_negative and conversation.status != "escalated":
        ticket = await escalation.open_ticket(
            store=state.store,
            notifier=state.notifier,
            settings=state.settings,
            ctx=ctx,
            conversation=conversation,
            reason="bad_feedback",
            summary="Negative CSAT on an un-escalated conversation (recovery). "
                    + (f"Reason: {body.reason}. " if body.reason else "")
                    + (f"Comment: {body.comment}" if body.comment else ""),
        )
        ticket_id = ticket.id
    return JSONResponse({"ok": True, "ticketId": ticket_id})


# ---------------------------------------------------------------------------
# POST /v1/erasure  (§7) — GDPR/CCPA per-subject erasure
# ---------------------------------------------------------------------------

@router.post("/v1/erasure")
async def erasure(request: Request) -> JSONResponse:
    state = request.app.state
    ctx, raw = await _authenticated(request)
    try:
        body = ErasureRequest.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="invalid request body") from exc
    # A subject may erase itself; a verified owner may erase any subject in
    # their tenant (the app backend mints the token either way).
    if body.subjectId != ctx.subject.id and ctx.subject.role != "owner":
        raise HTTPException(status_code=403, detail="forbidden")
    erased = await state.store.erase_subject(ctx.app_id, ctx.tenant_id, body.subjectId)
    return JSONResponse({"ok": True, "erased": erased})


# ---------------------------------------------------------------------------
# Operator surface (internal; Foundry-side only — guarded by a static token)
# ---------------------------------------------------------------------------

def _require_operator(request: Request) -> None:
    expected = request.app.state.settings.operator_token
    if not expected:
        raise HTTPException(status_code=503, detail="operator surface not configured")
    header = request.headers.get("authorization", "")
    supplied = header[len("Bearer "):] if header.startswith("Bearer ") else ""
    if not hmac_mod.compare_digest(
        hashlib.sha256(supplied.encode()).digest(),
        hashlib.sha256(expected.encode()).digest(),
    ):
        raise HTTPException(status_code=401, detail="unauthorized")


@router.get("/internal/tickets")
async def list_tickets(request: Request, status: str | None = None) -> JSONResponse:
    _require_operator(request)
    tickets = await request.app.state.store.list_tickets(status=status)
    return JSONResponse({
        "tickets": [
            {**t.webhook_shape(), "appId": t.app_id, "createdAt": _iso(t.created_at)}
            for t in tickets
        ]
    })


@router.post("/internal/tickets/{ticket_id}/reply")
async def operator_reply(ticket_id: str, request: Request) -> JSONResponse:
    """Operator answers a ticket (via Telegram flow or any Foundry surface):
    appends an `operator` message, marks the ticket replied, fires
    `ticket.replied` — the client app relays it (in-app + email)."""
    state = request.app.state
    _require_operator(request)
    try:
        body = OperatorReplyRequest.model_validate_json(await request.body())
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="invalid request body") from exc

    ticket = await state.store.get_ticket_any_tenant(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="ticket not found")

    await state.store.add_message(Message(
        id=new_id("msg"),
        conversation_id=ticket.conversation_id,
        app_id=ticket.app_id,
        tenant_id=ticket.tenant_id,
        sender="operator",
        body=body.reply,
    ))
    updated = await state.store.set_ticket_replied(ticket_id, body.reply)
    # Dedupe on the reply content: retries of THIS reply collapse, but a
    # later, different reply still goes out (receivers upsert by id+type).
    reply_digest = hashlib.sha256(body.reply.encode()).hexdigest()[:16]
    await state.store.enqueue_webhook(WebhookDelivery(
        id=new_id("whd"),
        app_id=ticket.app_id,
        event_type="ticket.replied",
        dedupe_key=f"{ticket.id}:ticket.replied:{reply_digest}",
        payload={
            "type": "ticket.replied",
            "ticket": updated.webhook_shape(),
            "ts": int(now_utc().timestamp()),
        },
    ))
    return JSONResponse({"ok": True, "ticket": updated.webhook_shape()})


@router.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse({"ok": True})
