"""§4: all three triggers create a ticket + Telegram notification +
data-escalation stream part + ticket.created webhook; operator replies fire
ticket.replied."""
from __future__ import annotations

import json

from services.support_api.agent import Escalate, TextDelta, Usage
from services.support_api.escalation import is_repetitive_loop, wants_human

from conftest import (
    OPERATOR_TOKEN,
    auth_headers,
    chat_events,
    find,
    joined_text,
)


def _assert_escalated(events, store, notifier):
    escalation_part = find(events, "data-escalation")
    assert escalation_part is not None
    ticket_id = escalation_part["data"]["ticketId"]
    ticket = store.tickets[ticket_id]
    assert ticket.status == "open"
    assert store.conversations[ticket.conversation_id].status == "escalated"
    assert any("SUPPORT TICKET" in text for text in notifier.sent)
    created = [w for w in store.webhooks.values() if w.event_type == "ticket.created"]
    assert len(created) == 1
    assert created[0].payload["ticket"]["id"] == ticket_id
    assert "representatives will be with you shortly" in joined_text(events)
    return ticket


def test_trigger1_widget_sentinel(client, private_pem, store, notifier, agent):
    events = chat_events(client, private_pem, "__human__")
    _assert_escalated(events, store, notifier)
    assert agent.calls == 0  # explicit request skips the model entirely


def test_trigger1_natural_language(client, private_pem, store, notifier):
    events = chat_events(client, private_pem, "I want to talk to a human please")
    _assert_escalated(events, store, notifier)


def test_wants_human_matrix():
    assert wants_human("__human__")
    assert wants_human("can I speak with a person?")
    assert wants_human("let me chat to someone")
    assert wants_human("I need a real human")
    assert not wants_human("how do I add a human-readable label?")
    assert not wants_human("what are your prices?")


def test_trigger2_low_confidence_from_agent(client, private_pem, store, notifier, agent):
    agent.events = [
        TextDelta("I couldn't find that in our documentation."),
        Escalate(reason="low_confidence", summary="KB has no answer for X."),
        Usage(tokens=10),
    ]
    events = chat_events(client, private_pem, "what is your enterprise SLA?")
    ticket = _assert_escalated(events, store, notifier)
    assert ticket.summary == "KB has no answer for X."
    # The ungroundable question got a refusal-to-guess + escalation, and the
    # model text is preserved ahead of the holding message.
    assert joined_text(events).startswith("I couldn't find that")


def test_trigger3_frustration_from_agent(client, private_pem, store, notifier, agent):
    agent.events = [
        TextDelta("I'm sorry this has been frustrating."),
        Escalate(reason="frustration", summary="User is upset about billing."),
        Usage(tokens=10),
    ]
    events = chat_events(client, private_pem, "this is USELESS. third time asking!!")
    _assert_escalated(events, store, notifier)


def test_trigger3_repetitive_loop_detected_deterministically(
    client, private_pem, store, notifier, agent
):
    question = "why is my menu not showing?"
    events = chat_events(client, private_pem, question)
    conv_id = find(events, "data-meta")["data"]["conversationId"]
    chat_events(client, private_pem, question, conversation_id=conv_id)
    events3 = chat_events(client, private_pem, question, conversation_id=conv_id)
    _assert_escalated(events3, store, notifier)
    assert agent.calls == 2  # third turn escalated before reaching the model


def test_loop_detector_needs_three_similar_turns():
    from services.support_api.models import Message

    def msg(body):
        return Message(id="m", conversation_id="c", app_id="a", tenant_id="t",
                       sender="user", body=body)

    same = "where is my invoice?"
    assert is_repetitive_loop([msg(same), msg(same)], same)
    assert not is_repetitive_loop([msg(same)], same)
    assert not is_repetitive_loop([msg(same), msg("how do I upgrade?")], same)


def test_operator_reply_fires_ticket_replied(client, private_pem, store, notifier):
    events = chat_events(client, private_pem, "__human__")
    ticket_id = find(events, "data-escalation")["data"]["ticketId"]

    resp = client.post(
        f"/internal/tickets/{ticket_id}/reply",
        content=json.dumps({"reply": "Fixed it for you — sorry about that!"}),
        headers={"Authorization": f"Bearer {OPERATOR_TOKEN}"},
    )
    assert resp.status_code == 200
    assert resp.json()["ticket"]["status"] == "replied"

    ticket = store.tickets[ticket_id]
    assert ticket.status == "replied"
    conv_messages = store.messages[ticket.conversation_id]
    assert conv_messages[-1].sender == "operator"
    replied = [w for w in store.webhooks.values() if w.event_type == "ticket.replied"]
    assert len(replied) == 1
    assert replied[0].payload["ticket"]["reply"] == "Fixed it for you — sorry about that!"


def test_operator_surface_requires_token(client, private_pem):
    resp = client.post("/internal/tickets/tick_x/reply",
                       content=b'{"reply":"hi"}',
                       headers={"Authorization": "Bearer wrong-token"})
    assert resp.status_code == 401
    resp = client.get("/internal/tickets")
    assert resp.status_code == 401


def test_operator_ticket_listing(client, private_pem, store):
    chat_events(client, private_pem, "__human__")
    resp = client.get("/internal/tickets?status=open",
                      headers={"Authorization": f"Bearer {OPERATOR_TOKEN}"})
    assert resp.status_code == 200
    tickets = resp.json()["tickets"]
    assert len(tickets) == 1 and tickets[0]["status"] == "open"
