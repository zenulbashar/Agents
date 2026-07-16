"""§3: /v1/chat streams UI Message Stream v1; conversations resume; tenancy
scoping; refusal + budget/rate limits."""
from __future__ import annotations

import json

from services.support_api.agent import REFUSAL_TEXT

from conftest import (
    TENANT,
    auth_headers,
    chat_events,
    find,
    joined_text,
    parse_sse,
    post_chat,
)


def test_new_conversation_streams_v1_shape(client, private_pem, store):
    resp = post_chat(client, private_pem, "How do I reset my password?")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.headers["x-vercel-ai-ui-message-stream"] == "v1"
    assert resp.headers["cache-control"] == "no-cache"

    events = parse_sse(resp.text)
    types = [e["type"] if isinstance(e, dict) else e for e in events]
    assert types[0] == "start"
    assert types[1] == "data-meta"          # first event of a new conversation
    assert types[2] == "text-start"
    assert types[-1] == "[DONE]"
    assert types[-2] == "finish"
    assert "text-end" in types
    assert types.index("text-start") < types.index("text-delta") < types.index("text-end")

    assert joined_text(events) == "Hello world."
    sources = find(events, "data-sources")
    assert sources["data"][0]["title"] == "About prompt2eat"

    conv_id = find(events, "data-meta")["data"]["conversationId"]
    assert conv_id.startswith("conv_")

    # Both turns persisted, assistant with citations attached.
    messages = store.messages[conv_id]
    assert [m.sender for m in messages] == ["user", "assistant"]
    assert messages[1].body == "Hello world."
    assert messages[1].sources[0]["title"] == "About prompt2eat"


def test_resumed_conversation_has_no_meta_part(client, private_pem):
    first = chat_events(client, private_pem, "hello")
    conv_id = find(first, "data-meta")["data"]["conversationId"]
    second = chat_events(client, private_pem, "and a follow-up",
                         conversation_id=conv_id)
    assert find(second, "data-meta") is None
    assert joined_text(second) == "Hello world."


def test_conversation_of_other_subject_is_404(client, private_pem):
    events = chat_events(client, private_pem, "hello")
    conv_id = find(events, "data-meta")["data"]["conversationId"]
    resp = post_chat(client, private_pem, "hi", conversation_id=conv_id,
                     subject={"role": "anon", "id": "someone_else"})
    assert resp.status_code == 404


def test_conversation_of_other_tenant_is_404(client, private_pem):
    events = chat_events(client, private_pem, "hello")
    conv_id = find(events, "data-meta")["data"]["conversationId"]
    resp = post_chat(client, private_pem, "hi", conversation_id=conv_id,
                     tenant_id="venue_OTHER")
    assert resp.status_code == 404


def test_tenancy_comes_from_token_not_body(client, private_pem, store):
    # A tenant_id smuggled into the body must be ignored: the conversation is
    # created under the token's tenant.
    body = json.dumps({"conversationId": None, "department": "tech",
                       "message": "hi", "tenant_id": "venue_EVIL"}).encode()
    resp = client.post("/v1/chat", content=body,
                       headers=auth_headers(private_pem, body))
    assert resp.status_code == 200
    conv_id = find(parse_sse(resp.text), "data-meta")["data"]["conversationId"]
    assert store.conversations[conv_id].tenant_id == TENANT


def test_unknown_department_is_422(client, private_pem):
    resp = post_chat(client, private_pem, "hi", department="hr")
    assert resp.status_code == 422


def test_missing_auth_is_401(client):
    resp = client.post("/v1/chat", content=b"{}")
    assert resp.status_code == 401


def test_harmful_input_gets_refusal_without_model_call(client, private_pem, agent):
    agent.harmful = True
    events = chat_events(client, private_pem, "do something harmful")
    assert joined_text(events) == REFUSAL_TEXT
    assert find(events, "data-escalation") is None
    assert agent.calls == 0  # pre-screen blocked before the main model


def test_get_conversation_resume_payload(client, private_pem):
    events = chat_events(client, private_pem, "hello")
    conv_id = find(events, "data-meta")["data"]["conversationId"]
    resp = client.get(f"/v1/conversations/{conv_id}",
                      headers=auth_headers(private_pem, b""))
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["conversation"]["id"] == conv_id
    assert payload["conversation"]["status"] == "active"
    assert [m["sender"] for m in payload["messages"]] == ["user", "assistant"]


def test_get_conversation_other_subject_404(client, private_pem):
    events = chat_events(client, private_pem, "hello")
    conv_id = find(events, "data-meta")["data"]["conversationId"]
    resp = client.get(f"/v1/conversations/{conv_id}",
                      headers=auth_headers(private_pem, b"",
                                           subject={"role": "anon", "id": "nope"}))
    assert resp.status_code == 404


def test_daily_budget_exhausted_is_429(settings, registry, store, agent,
                                       notifier, private_pem):
    from fastapi.testclient import TestClient

    from services.support_api.app import create_app

    settings.daily_token_budget = 100
    app = create_app(settings, store=store, agent=agent, notifier=notifier,
                     registry=registry)
    with TestClient(app) as client:
        events = chat_events(client, private_pem, "hello")   # records 42 tokens
        conv_id = find(events, "data-meta")["data"]["conversationId"]
        # Push usage past the cap, next request must be refused pre-stream.
        store.usage.append({"app_id": "prompt2eat", "tenant_id": TENANT,
                            "conversation_id": conv_id, "tokens": 100,
                            "day": store.usage[0]["day"]})
        resp = post_chat(client, private_pem, "hello again")
        assert resp.status_code == 429


def test_subject_rate_limit_is_429(settings, registry, store, agent, notifier,
                                   private_pem):
    from fastapi.testclient import TestClient

    from services.support_api.app import create_app

    settings.subject_rate_per_minute = 2
    app = create_app(settings, store=store, agent=agent, notifier=notifier,
                     registry=registry)
    with TestClient(app) as client:
        assert post_chat(client, private_pem, "one").status_code == 200
        assert post_chat(client, private_pem, "two").status_code == 200
        assert post_chat(client, private_pem, "three").status_code == 429


def test_midstream_agent_error_yields_error_event(client, private_pem, agent):
    class Boom:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise RuntimeError("model exploded")

    agent.stream_reply = lambda **kwargs: Boom()
    resp = post_chat(client, private_pem, "hello")
    assert resp.status_code == 200  # headers were already streamed
    events = parse_sse(resp.text)
    error = find(events, "error")
    assert error is not None and error["errorText"]
    assert events[-1] == "[DONE]"
