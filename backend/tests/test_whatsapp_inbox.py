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
    ]:
        assert public_client.request(method, url, json=body).status_code in {401, 403}
        assert public_client.request(method, url, json=body, headers={"Authorization": "Bearer invalid"}).status_code in {401, 403}


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
