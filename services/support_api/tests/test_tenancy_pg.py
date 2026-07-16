"""§7 acceptance: a token for tenant A can never read/write tenant B (RLS).

Integration test — needs a real Postgres and both roles. Set:
    SUPPORT_TEST_MAINT_DSN=postgresql://owner:pw@host/db      (schema owner)
    SUPPORT_TEST_APP_DSN=postgresql://support_api_app:pw@host/db
Skipped when unset (e.g. CI without a database).
"""
from __future__ import annotations

import os

import pytest

APP_DSN = os.environ.get("SUPPORT_TEST_APP_DSN", "")
MAINT_DSN = os.environ.get("SUPPORT_TEST_MAINT_DSN", "")

pytestmark = pytest.mark.skipif(
    not (APP_DSN and MAINT_DSN),
    reason="set SUPPORT_TEST_APP_DSN / SUPPORT_TEST_MAINT_DSN to run RLS tests",
)


@pytest.fixture()
async def pg_store():
    from services.support_api.db import PgStore

    store = PgStore(APP_DSN, MAINT_DSN)
    await store.open()
    await store.apply_schema()
    yield store
    await store.close()


async def test_rls_blocks_cross_tenant_reads_and_writes(pg_store):
    from services.support_api.models import Message, new_id
    from services.support_api.store import build_conversation

    conv = build_conversation("prompt2eat", "tenant_A", "subj_1", None, "tech")
    await pg_store.create_conversation(conv)
    await pg_store.add_message(Message(
        id=new_id("msg"), conversation_id=conv.id, app_id="prompt2eat",
        tenant_id="tenant_A", sender="user", body="secret question",
    ))

    # Tenant B sees nothing — not even existence.
    assert await pg_store.get_conversation("prompt2eat", "tenant_B", "subj_1", conv.id) is None
    assert await pg_store.get_messages("prompt2eat", "tenant_B", conv.id) == []
    # Another app sees nothing either.
    assert await pg_store.get_conversation("roster", "tenant_A", "subj_1", conv.id) is None

    # Cross-tenant write is silently a no-op under RLS (0 rows match).
    await pg_store.set_conversation_status("prompt2eat", "tenant_B", conv.id, "closed")
    same = await pg_store.get_conversation("prompt2eat", "tenant_A", "subj_1", conv.id)
    assert same is not None and same.status == "active"

    # Erasure from tenant B touches nothing; from tenant A it cascades.
    assert (await pg_store.erase_subject("prompt2eat", "tenant_B", "subj_1"))["conversations"] == 0
    assert (await pg_store.erase_subject("prompt2eat", "tenant_A", "subj_1"))["conversations"] == 1


async def test_jti_replay_unique_violation(pg_store):
    jti = f"test-{os.urandom(8).hex()}"
    assert await pg_store.consume_jti("prompt2eat", jti) is True
    assert await pg_store.consume_jti("prompt2eat", jti) is False
