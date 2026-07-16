"""Shared fixtures: a fake client app (Ed25519 keypair + HMAC secret), a
scripted agent, the in-memory store, and helpers to mint tokens / sign
bodies / parse SSE streams."""
from __future__ import annotations

import hashlib
import hmac
import json
import sys
import time
import uuid
from pathlib import Path

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from services.support_api.agent import Escalate, Sources, TextDelta, Usage  # noqa: E402
from services.support_api.app import create_app  # noqa: E402
from services.support_api.notifier import NullNotifier  # noqa: E402
from services.support_api.settings import AppConfig, AppRegistry, Settings  # noqa: E402
from services.support_api.store import MemoryStore  # noqa: E402

APP_ID = "prompt2eat"
TENANT = "venue_abc123"
HMAC_SECRET = b"test-hmac-secret"
WEBHOOK_SECRET = b"test-webhook-secret"
OPERATOR_TOKEN = "test-operator-token"
KB_DIR = REPO_ROOT / "services" / "support_api" / "kb" / "prompt2eat"


@pytest.fixture(scope="session")
def private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


@pytest.fixture(scope="session")
def private_pem(private_key) -> bytes:
    return private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


@pytest.fixture()
def registry(private_key) -> AppRegistry:
    return AppRegistry(apps={
        APP_ID: AppConfig(
            app_id=APP_ID,
            public_key=private_key.public_key(),
            hmac_secret=HMAC_SECRET,
            webhook_url="https://client.example/api/support/webhook",
            webhook_secret=WEBHOOK_SECRET,
            departments=("tech", "sales", "billing"),
            kb_dir=KB_DIR,
        )
    })


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        store_backend="memory",
        workers_enabled=False,
        operator_token=OPERATOR_TOKEN,
        subject_rate_per_minute=1000,
        daily_token_budget=1_000_000,
        conversation_token_budget=100_000,
        public_base_url="https://support.foundry.test",
    )


@pytest.fixture()
def store() -> MemoryStore:
    return MemoryStore()


@pytest.fixture()
def notifier() -> NullNotifier:
    return NullNotifier()


class FakeAgent:
    """Scripted agent. Set .events to override the default happy path,
    .harmful to trip the pre-screen."""

    available = True

    def __init__(self) -> None:
        self.harmful = False
        self.events: list | None = None
        self.calls = 0

    async def prescreen(self, text: str) -> bool:
        return self.harmful

    async def stream_reply(self, *, history, kb_docs, department, locale):
        self.calls += 1
        events = self.events if self.events is not None else [
            TextDelta("Hello "),
            TextDelta("world."),
            Sources([{"title": "About prompt2eat", "url": "https://www.prompt2eat.com/about"}]),
            Usage(tokens=42),
        ]
        for event in events:
            yield event


@pytest.fixture()
def agent() -> FakeAgent:
    return FakeAgent()


@pytest.fixture()
def client(settings, registry, store, agent, notifier):
    app = create_app(settings, store=store, agent=agent, notifier=notifier, registry=registry)
    with TestClient(app) as test_client:
        yield test_client


# ---- helpers ---------------------------------------------------------------

def mint_token(
    private_pem: bytes,
    *,
    app_id: str = APP_ID,
    tenant_id: str = TENANT,
    subject: dict | None = None,
    ttl: int = 60,
    aud: str = "foundry-support",
    algorithm: str = "EdDSA",
    key: bytes | None = None,
    **claim_overrides,
) -> str:
    now = int(time.time())
    claims = {
        "iss": app_id,
        "aud": aud,
        "iat": now,
        "exp": now + ttl,
        "jti": str(uuid.uuid4()),
        "app_id": app_id,
        "tenant_id": tenant_id,
        "subject": subject or {
            "role": "owner", "id": "user_xyz", "email": "o@example.com", "name": "Alex",
        },
    }
    claims.update(claim_overrides)
    return pyjwt.encode(claims, key or private_pem, algorithm=algorithm)


def sign_body(body: bytes, secret: bytes = HMAC_SECRET) -> str:
    return hmac.new(secret, body, hashlib.sha256).hexdigest()


def auth_headers(private_pem: bytes, body: bytes, **token_kwargs) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {mint_token(private_pem, **token_kwargs)}",
        "X-Signature": sign_body(body),
        "Content-Type": "application/json",
    }


def parse_sse(text: str) -> list:
    events: list = []
    for line in text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[len("data: "):]
        events.append("[DONE]" if payload == "[DONE]" else json.loads(payload))
    return events


def post_chat(client, private_pem, message: str, *, conversation_id: str | None = None,
              department: str = "tech", **token_kwargs):
    body = json.dumps({
        "conversationId": conversation_id,
        "department": department,
        "message": message,
    }).encode()
    return client.post("/v1/chat", content=body,
                       headers=auth_headers(private_pem, body, **token_kwargs))


def chat_events(client, private_pem, message: str, **kwargs) -> list:
    resp = post_chat(client, private_pem, message, **kwargs)
    assert resp.status_code == 200, resp.text
    return parse_sse(resp.text)


def joined_text(events: list) -> str:
    return "".join(e["delta"] for e in events
                   if isinstance(e, dict) and e["type"] == "text-delta")


def find(events: list, event_type: str) -> dict | None:
    return next((e for e in events
                 if isinstance(e, dict) and e["type"] == event_type), None)
