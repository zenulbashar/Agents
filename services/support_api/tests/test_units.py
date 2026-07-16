"""Unit coverage: SSE encoding shapes, KB parsing/document blocks, retention."""
from __future__ import annotations

import json
from datetime import timedelta

from services.support_api import sse
from services.support_api.kb import document_blocks, load_kb
from services.support_api.models import Message, now_utc
from services.support_api.retention import sweep_once
from services.support_api.store import MemoryStore, build_conversation


def _decode(line: str) -> dict:
    assert line.startswith("data: ") and line.endswith("\n\n")
    return json.loads(line[len("data: "):])


def test_sse_event_shapes():
    assert _decode(sse.start("m1")) == {"type": "start", "messageId": "m1"}
    assert _decode(sse.text_start("t1")) == {"type": "text-start", "id": "t1"}
    assert _decode(sse.text_delta("t1", "hi")) == {
        "type": "text-delta", "id": "t1", "delta": "hi"}
    assert _decode(sse.text_end("t1")) == {"type": "text-end", "id": "t1"}
    assert _decode(sse.data_part("meta", {"conversationId": "c1"})) == {
        "type": "data-meta", "data": {"conversationId": "c1"}}
    assert _decode(sse.finish()) == {"type": "finish"}
    assert _decode(sse.error("boom")) == {"type": "error", "errorText": "boom"}
    assert sse.DONE == "data: [DONE]\n\n"
    assert sse.STREAM_HEADERS["x-vercel-ai-ui-message-stream"] == "v1"


def test_kb_load_and_front_matter(tmp_path):
    (tmp_path / "common").mkdir()
    (tmp_path / "tech").mkdir()
    (tmp_path / "common" / "faq.md").write_text(
        "---\ntitle: The FAQ\nurl: https://x.example/faq\n---\nbody here")
    (tmp_path / "tech" / "reset-password.md").write_text("no front matter")
    (tmp_path / "billing").mkdir()
    (tmp_path / "billing" / "invoices.md").write_text("billing only")

    docs = load_kb(tmp_path, "tech")
    assert [d.title for d in docs] == ["The FAQ", "Reset Password"]
    assert docs[0].url == "https://x.example/faq"
    assert docs[0].text == "body here"
    assert all("billing only" not in d.text for d in docs)  # other dept excluded


def test_document_blocks_citations_and_cached_prefix(tmp_path):
    (tmp_path / "common").mkdir()
    (tmp_path / "common" / "a.md").write_text("doc a")
    (tmp_path / "common" / "b.md").write_text("doc b")
    blocks = document_blocks(load_kb(tmp_path, "tech"))
    assert all(b["type"] == "document" for b in blocks)
    assert all(b["citations"] == {"enabled": True} for b in blocks)
    assert "cache_control" not in blocks[0]
    assert blocks[-1]["cache_control"] == {"type": "ephemeral"}  # cached prefix


async def test_retention_sweep_purges_old_conversations(settings):
    store = MemoryStore()
    old = build_conversation("prompt2eat", "venue_a", "s1", None, "tech")
    old.last_message_at = now_utc() - timedelta(days=120)
    fresh = build_conversation("prompt2eat", "venue_a", "s1", None, "tech")
    await store.create_conversation(old)
    await store.create_conversation(fresh)
    await store.add_message(Message(id="m1", conversation_id=fresh.id,
                                    app_id="prompt2eat", tenant_id="venue_a",
                                    sender="user", body="hi"))
    store.jtis[("prompt2eat", "old-jti")] = now_utc() - timedelta(hours=1)
    store.jtis[("prompt2eat", "new-jti")] = now_utc()

    result = await sweep_once(store, settings)
    assert result == {"conversations": 1, "jtis": 1}
    assert old.id not in store.conversations
    assert fresh.id in store.conversations
    assert ("prompt2eat", "new-jti") in store.jtis
