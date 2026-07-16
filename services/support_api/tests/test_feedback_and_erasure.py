"""§8 feedback (one per conversation, bad => recovery ticket) and §7 erasure."""
from __future__ import annotations

import json

from conftest import auth_headers, chat_events, find


def _post_feedback(client, private_pem, conversation_id, rating, **extra):
    body = json.dumps({"conversationId": conversation_id, "rating": rating,
                       **extra}).encode()
    return client.post("/v1/feedback", content=body,
                       headers=auth_headers(private_pem, body))


def _new_conversation(client, private_pem, message="hello"):
    events = chat_events(client, private_pem, message)
    return find(events, "data-meta")["data"]["conversationId"]


def test_good_feedback_stored_and_upserted(client, private_pem, store):
    conv_id = _new_conversation(client, private_pem)
    assert _post_feedback(client, private_pem, conv_id, "good").status_code == 200
    assert store.feedback[conv_id]["rating"] == "good"
    # One per conversation: a second submission replaces, not duplicates.
    assert _post_feedback(client, private_pem, conv_id, 5).status_code == 200
    assert store.feedback[conv_id]["rating"] == "5"
    assert len(store.feedback) == 1


def test_bad_feedback_auto_opens_recovery_ticket(client, private_pem, store, notifier):
    conv_id = _new_conversation(client, private_pem)
    resp = _post_feedback(client, private_pem, conv_id, "bad",
                          reason="not-helpful", comment="didn't answer me")
    assert resp.status_code == 200
    ticket_id = resp.json()["ticketId"]
    assert ticket_id is not None
    assert store.tickets[ticket_id].conversation_id == conv_id
    assert store.conversations[conv_id].status == "escalated"
    assert any(w.event_type == "ticket.created" for w in store.webhooks.values())


def test_bad_feedback_on_escalated_conversation_opens_nothing(client, private_pem, store):
    conv_id = _new_conversation(client, private_pem, "__human__")  # already escalated
    tickets_before = len(store.tickets)
    resp = _post_feedback(client, private_pem, conv_id, 1)
    assert resp.status_code == 200
    assert resp.json()["ticketId"] is None
    assert len(store.tickets) == tickets_before


def test_feedback_unknown_conversation_404(client, private_pem):
    assert _post_feedback(client, private_pem, "conv_nope", "good").status_code == 404


def test_invalid_rating_422(client, private_pem):
    conv_id = _new_conversation(client, private_pem)
    assert _post_feedback(client, private_pem, conv_id, 9).status_code == 422


def test_subject_can_erase_itself(client, private_pem, store):
    conv_id = _new_conversation(client, private_pem)
    body = json.dumps({"subjectId": "user_xyz"}).encode()
    resp = client.post("/v1/erasure", content=body,
                       headers=auth_headers(private_pem, body))
    assert resp.status_code == 200
    assert resp.json()["erased"]["conversations"] == 1
    assert conv_id not in store.conversations
    assert conv_id not in store.messages


def test_owner_can_erase_other_subject_diner_cannot(client, private_pem, store):
    _new_conversation(client, private_pem)  # owned by user_xyz
    body = json.dumps({"subjectId": "user_xyz"}).encode()
    diner = {"role": "diner", "id": "diner_1", "email": "d@example.com"}
    resp = client.post("/v1/erasure", content=body,
                       headers=auth_headers(private_pem, body, subject=diner))
    assert resp.status_code == 403
    assert len(store.conversations) == 1

    owner = {"role": "owner", "id": "boss_1", "email": "b@example.com"}
    resp = client.post("/v1/erasure", content=body,
                       headers=auth_headers(private_pem, body, subject=owner))
    assert resp.status_code == 200
    assert len(store.conversations) == 0


def test_erasure_scoped_to_tenant(client, private_pem, store):
    _new_conversation(client, private_pem)
    body = json.dumps({"subjectId": "user_xyz"}).encode()
    resp = client.post("/v1/erasure", content=body,
                       headers=auth_headers(private_pem, body, tenant_id="venue_OTHER"))
    assert resp.status_code == 200
    assert resp.json()["erased"]["conversations"] == 0
    assert len(store.conversations) == 1  # other tenant's token touched nothing
