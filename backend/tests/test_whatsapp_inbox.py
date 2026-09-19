from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from channels.whatsapp_channel import IncomingText
from core.config import settings
from integrations.whatsapp.client import WhatsAppDeliveryError
from models.atendimento import Conversation, Message, utc_now
from services import whatsapp_human_service as human, whatsapp_inbox_service as inbox, ai_agent
from services.customer_service import create_web_session
from test_catalog_tools import create_product


@pytest.fixture
def conversation(db, monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "1234567")
    monkeypatch.setattr(human, "send_text", lambda *_: "welcome")
    monkeypatch.setattr(ai_agent, "respond", lambda *_: pytest.fail("WhatsApp must not call AI"))
    human.receive_messages(db, [IncomingText("1234567", "5599988887777", "incoming-1", "Olá", int(utc_now().timestamp()))])
    return db.scalar(select(Conversation))


def test_all_inbox_routes_require_admin(public_client):
    base = f"/admin/conversations/{uuid4()}"
    for method, url, body in [
        ("GET", "/admin/conversations?channel=whatsapp", None), ("GET", base + "/messages", None),
        ("POST", base + "/claim", {}), ("POST", base + "/close", {}),
        ("POST", base + "/messages", {"message_id": str(uuid4()), "message": "Olá"}),
        ("PATCH", base, {"status": "AI"}),
        ("PATCH", base + "/ai-mode", {"ai_mode": "AUTO"}),
        ("POST", base + "/ai-suggestion", {}),
    ]:
        assert public_client.request(method, url, json=body).status_code in {401, 403}
        assert public_client.request(method, url, json=body, headers={"Authorization": "Bearer invalid"}).status_code in {401, 403}


@pytest.mark.parametrize("attempts", [1, 2])
def test_detail_exposes_safe_ai_observability(client, db, conversation, monkeypatch, attempts):
    monkeypatch.setattr(settings, "AI_WHATSAPP_ENABLED", True)
    product = create_product(client, id=f"focus-{attempts}", title="Camiseta Gótica")
    conversation.ai_mode = "AUTO"
    conversation.status = "WAITING_HUMAN"
    conversation.handoff_reason = "LOW_CONFIDENCE"
    conversation.context = {
        "internal_secret": "never expose this",
        "conversation_v2": {
            "schema_version": 1,
            "last_decision": {"action": "CLARIFY", "reason_code": "AMBIGUOUS_PROCESS",
                              "source_message_id": "internal-message-id"},
            "clarification": {"attempts": attempts, "kind": "PROCESS_TOPIC",
                              "options": ["compra"], "source_message_id": "internal-message-id"},
            "focus": {"product_ids": [product["id"]], "selected_product_id": product["id"]},
            "preferences": {"garment": "camiseta", "style_query": "gotico", "size": "M",
                            "color": "preto", "max_price": 80, "product_type": "catalogo",
                            "offer_only": True},
        },
    }
    db.add(Message(conversation_id=conversation.id, sender="assistant", content="Ativado",
                   extra_data={"event": "AI_ACTIVATED", "cycle": 1}))
    db.commit()

    payload = client.get(f"/admin/conversations/{conversation.id}/messages").json()
    state = payload["ai_state"]
    assert state["mode"] == "AUTO" and state["status"] == "WAITING_HUMAN"
    assert state["last_decision"] == {"action": "CLARIFY"}
    assert state["clarification"] == {"attempts": attempts, "max_attempts": 2, "kind": "PROCESS_TOPIC"}
    assert state["handoff"] == {"reason": "LOW_CONFIDENCE", "clarification_attempts": attempts}
    assert state["focus"]["selected_product"] == {"id": product["id"], "name": "Camiseta Gótica"}
    assert state["focus"]["presented_count"] == 1
    assert state["preferences"]["max_price"] == 80
    assert state["actions"]["resume_ai"] is True
    assert state["recent_events"][0]["type"] == "AI_ACTIVATED"
    assert "never expose this" not in str(payload)
    assert "internal-message-id" not in str(payload)


@pytest.mark.parametrize("reason", ["PURCHASE_INTENT", "HUMAN_REQUESTED"])
def test_detail_exposes_real_handoff_reason(client, db, conversation, reason):
    conversation.handoff_reason = reason
    conversation.status = "WAITING_HUMAN"
    db.commit()
    handoff = client.get(f"/admin/conversations/{conversation.id}/messages").json()["ai_state"]["handoff"]
    assert handoff == {"reason": reason, "clarification_attempts": None}


def test_legacy_empty_context_and_closed_actions_are_safe(client, db, conversation):
    conversation.context = {"conversation_v2": {"last_decision": {"action": "INTERNAL"}},
                            "provider_payload": {"prompt": "hidden"}}
    conversation.status = "CLOSED"
    conversation.ai_mode = "OFF"
    db.commit()
    payload = client.get(f"/admin/conversations/{conversation.id}/messages").json()
    state = payload["ai_state"]
    assert state["last_decision"] is None
    assert state["clarification"] is None and state["handoff"] is None
    assert state["focus"] == {"selected_product": None, "presented_count": 0, "products": []}
    assert state["preferences"] == {}
    assert state["actions"]["resume_ai"] is False
    assert "provider_payload" not in str(payload) and "hidden" not in str(payload)


@pytest.mark.parametrize(("mode", "status"), [
    ("AUTO", "AI"), ("AUTO", "WAITING_HUMAN"), ("ASSIST", "HUMAN"), ("OFF", "HUMAN"), ("OFF", "CLOSED"),
])
def test_detail_represents_mode_and_status_without_conflating_them(client, db, conversation, mode, status):
    conversation.ai_mode = mode
    conversation.status = status
    db.commit()
    state = client.get(f"/admin/conversations/{conversation.id}/messages").json()["ai_state"]
    assert state["mode"] == mode
    assert state["status"] == status


def test_list_history_claim_close_and_reopen(client, db, conversation, monkeypatch):
    base = f"/admin/conversations/{conversation.id}"
    rows = client.get("/admin/conversations?channel=whatsapp&status=WAITING_HUMAN").json()
    assert rows["items"][0]["phone"] == "5599988887777"
    assert "1234567" not in str(rows)
    history = client.get(base + "/messages?limit=1").json()
    assert history["has_more"] and len(history["messages"]) == 1
    older = client.get(base + "/messages?before=" + history["messages"][0]["id"]).json()
    assert older["messages"][0]["content"] == "Olá"
    assert "meta_message_id" not in str(history)
    assert client.post(base + "/claim").json()["status"] == "HUMAN"
    human.receive_messages(db, [IncomingText("1234567", "5599988887777", "incoming-2", "Mais", int(utc_now().timestamp()))])
    assert db.get(Conversation, conversation.id).status == "HUMAN"
    assert client.post(base + "/close").json()["status"] == "CLOSED"
    monkeypatch.setattr(human, "send_text", lambda *_: pytest.fail("Do not repeat the welcome"))
    human.receive_messages(db, [IncomingText("1234567", "5599988887777", "incoming-2", "Mais", int(utc_now().timestamp()))])
    assert db.get(Conversation, conversation.id).status == "CLOSED"
    human.receive_messages(db, [IncomingText("1234567", "5599988887777", "incoming-3", "Voltei", int(utc_now().timestamp()))])
    assert db.get(Conversation, conversation.id).status == "WAITING_HUMAN"
    assert db.query(Message).filter_by(sender="assistant").count() == 1


def test_inbox_order_pagination_and_account_isolation(client, db, conversation, monkeypatch):
    other = IncomingText("1234567", "5511999999999", "other", "Mais recente", int(utc_now().timestamp()))
    human.receive_messages(db, [other])
    client.post(f"/admin/conversations/{conversation.id}/claim")
    response = client.get("/admin/conversations?channel=whatsapp&limit=1")
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["has_more"]
    assert response.json()["items"][0]["status"] == "WAITING_HUMAN"
    second = client.get("/admin/conversations?channel=whatsapp&limit=1&offset=1").json()
    assert second["items"][0]["conversation_id"] == conversation.id
    monkeypatch.setattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "different-account")
    assert client.post(f"/admin/conversations/{conversation.id}/messages", json={
        "message_id": str(uuid4()), "message": "Teste"}).status_code == 409


def test_manual_message_is_reserved_before_send_and_deduplicated(client, db, conversation, monkeypatch):
    base = f"/admin/conversations/{conversation.id}"
    body = {"message_id": str(uuid4()), "message": "Temos sim!"}
    assert client.post(base + "/messages", json=body).status_code == 409
    client.post(base + "/claim")
    calls = []
    def send(recipient, text):
        assert not db.in_transaction()
        calls.append((recipient, text))
        return "wamid.manual"
    monkeypatch.setattr(inbox, "send_text", send)
    first = client.post(base + "/messages", json=body)
    assert first.status_code == 200 and first.json()["delivery_status"] == "sent"
    assert client.post(base + "/messages", json=body).json() == first.json()
    assert calls == [("5599988887777", "Temos sim!")]
    assert db.query(Message).filter_by(sender="human").count() == 1
    assert client.post(base + "/messages", json={**body, "message": "outro"}).status_code == 409
    for text in ["   ", "\x00", "x" * 2001]:
        assert client.post(base + "/messages", json={"message_id": str(uuid4()), "message": text}).status_code == 422


@pytest.mark.parametrize("error,expected", [
    (WhatsAppDeliveryError("whatsapp_rate_limited", retryable=True), "failed"),
    (WhatsAppDeliveryError("whatsapp_delivery_unknown", uncertain=True), "uncertain"),
    (RuntimeError("SECRET"), "uncertain"),
])
def test_meta_failure_is_persisted_without_duplicate_send(client, db, conversation, monkeypatch, error, expected, caplog):
    base = f"/admin/conversations/{conversation.id}"
    client.post(base + "/claim")
    calls = []
    def fail(*_):
        calls.append(True)
        raise error
    monkeypatch.setattr(inbox, "send_text", fail)
    body = {"message_id": str(uuid4()), "message": "Resposta"}
    response = client.post(base + "/messages", json=body)
    assert response.json()["delivery_status"] == expected
    assert client.post(base + "/messages", json=body).status_code == 200
    assert len(calls) == 1
    assert db.query(Message).filter_by(sender="customer").count() == 1
    assert "SECRET" not in caplog.text + response.text


def test_other_channel_invalid_ids_and_expired_window(client, db, conversation, monkeypatch):
    monkeypatch.setattr(inbox, "send_text", lambda *_: pytest.fail("No network"))
    web = create_web_session(db)
    body = {"message_id": str(uuid4()), "message": "Resposta"}
    for action in ["messages", "claim", "close"]:
        assert client.post(f"/admin/conversations/{web.conversation_id}/{action}", json=body if action == "messages" else {}).status_code == 404
    assert client.get("/admin/conversations/invalid/messages").status_code == 422
    assert client.get(f"/admin/conversations/{uuid4()}/messages").status_code == 404
    base = f"/admin/conversations/{conversation.id}"
    assert client.get(base + f"/messages?before={uuid4()}").status_code == 422
    client.post(base + "/claim")
    incoming = db.query(Message).filter_by(sender="customer").one()
    incoming.extra_data = {"received_timestamp": (utc_now() - timedelta(hours=25)).timestamp()}
    db.commit()
    assert client.post(base + "/messages", json=body).status_code == 409
