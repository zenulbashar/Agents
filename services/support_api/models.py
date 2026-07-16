"""Shared datatypes: auth context, rows, and request/response bodies."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Sender = Literal["user", "assistant", "operator", "system"]
ConversationStatus = Literal["active", "escalated", "closed"]
TicketStatus = Literal["open", "replied", "closed"]
EscalationReason = Literal["human_requested", "low_confidence", "frustration", "loop", "bad_feedback"]

_ID_RE = re.compile(r"^[A-Za-z0-9._:@-]{1,128}$")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


@dataclass(frozen=True)
class Subject:
    role: str  # owner | diner | anon
    id: str
    email: str | None = None
    name: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"role": self.role, "id": self.id, "email": self.email, "name": self.name}


@dataclass(frozen=True)
class AuthContext:
    """Verified per-request identity. Tenancy comes ONLY from here (D6)."""

    app_id: str
    tenant_id: str
    subject: Subject


@dataclass
class Conversation:
    id: str
    app_id: str
    tenant_id: str
    subject_id: str
    subject_email: str | None
    department: str
    status: ConversationStatus = "active"
    created_at: datetime = field(default_factory=now_utc)
    closed_at: datetime | None = None
    last_message_at: datetime = field(default_factory=now_utc)


@dataclass
class Message:
    id: str
    conversation_id: str
    app_id: str
    tenant_id: str
    sender: Sender
    body: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=now_utc)


@dataclass
class Ticket:
    id: str
    app_id: str
    tenant_id: str
    conversation_id: str
    department: str
    summary: str
    subject: dict[str, Any]
    status: TicketStatus = "open"
    reply: str | None = None
    created_at: datetime = field(default_factory=now_utc)
    replied_at: datetime | None = None

    def webhook_shape(self) -> dict[str, Any]:
        shape: dict[str, Any] = {
            "id": self.id,
            "conversationId": self.conversation_id,
            "tenantId": self.tenant_id,
            "department": self.department,
            "summary": self.summary,
            "status": self.status,
        }
        if self.reply is not None:
            shape["reply"] = self.reply
        return shape


@dataclass
class WebhookDelivery:
    id: str
    app_id: str
    event_type: str
    dedupe_key: str
    payload: dict[str, Any]
    status: str = "pending"  # pending | delivered | failed
    attempts: int = 0
    next_attempt_at: datetime = field(default_factory=now_utc)
    created_at: datetime = field(default_factory=now_utc)


# ---- request bodies -------------------------------------------------------

class ChatRequest(BaseModel):
    conversationId: str | None = None
    department: Literal["tech", "sales", "billing"]
    message: str = Field(min_length=1, max_length=8000)
    locale: str | None = Field(default=None, max_length=32)


class FeedbackRequest(BaseModel):
    conversationId: str
    rating: Literal["good", "bad"] | int
    reason: str | None = Field(default=None, max_length=500)
    comment: str | None = Field(default=None, max_length=4000)

    @field_validator("rating")
    @classmethod
    def _rating_range(cls, v):
        if isinstance(v, int) and not 1 <= v <= 5:
            raise ValueError("numeric rating must be 1-5")
        return v

    @property
    def is_negative(self) -> bool:
        return self.rating == "bad" or (isinstance(self.rating, int) and self.rating <= 2)


class ErasureRequest(BaseModel):
    subjectId: str

    @field_validator("subjectId")
    @classmethod
    def _subject_shape(cls, v: str) -> str:
        if not _ID_RE.match(v):
            raise ValueError("invalid subject id")
        return v


class OperatorReplyRequest(BaseModel):
    reply: str = Field(min_length=1, max_length=8000)
