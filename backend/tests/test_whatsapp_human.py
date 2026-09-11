from datetime import datetime, timedelta, timezone
import logging

import pytest

from models.atendimento import ChannelIdentity, Conversation, Customer, DeliveryJob, Message
from services import ai_agent, delivery_service, conversation_service, whatsapp_human_service as human
from services.customer_service import SupportError
from integrations.whatsapp.client import WhatsAppDeliveryError
from core.config import settings
from test_whatsapp import whatsapp_settings, wa_client, payload, post_event


@pytest.fixture(autouse=True)
def no_whatsapp_ai(monkeypatch):
    monkeypatch.setattr(ai_agent, "respond", lambda *_: pytest.fail("WhatsApp must never call AI"))


def test_initial_greeting_exactly_once_without_worker(wa_client, db, monkeypatch):
    sent = []
    def send(recipient, text):
        assert not db.in_transaction()
        sent.append((recipient, text))
        return "wamid.initial"
    monkeypatch.setattr(human, "send_text", send)
    initial = payload()
    assert post_event(wa_client, initial).status_code == 200
    assert post_event(wa_client, initial).status_code == 200
    for index in range(3):
        assert post_event(wa_client, payload(message_id=f"wamid.next-{index}")).status_code == 200
    assert sent == [("5599988887777", human.WELCOME_TEXT)]
    assert human.WELCOME_TEXT == ("Olá! 🖤 Recebemos sua mensagem.\n\nEm breve, um atendente da Dark District entrará em contato com você.\n\nObrigado pela preferência.\nDark District — Vista o seu lado obscuro.")
    assert db.query(Customer).count() == db.query(ChannelIdentity).count() == db.query(Conversation).count() == 1
    assert db.query(Conversation).one().status == "HUMAN"
    assert db.query(Message).filter_by(sender="customer").count() == 4
    greeting = db.query(Message).filter_by(sender="assistant").one()
    assert greeting.extra_data["delivery_status"] == "sent"
    assert greeting.extra_data["meta_message_id"] == "wamid.initial"
    assert db.query(DeliveryJob).count() == 0


@pytest.mark.parametrize("error", [WhatsAppDeliveryError("whatsapp_rate_limited", retryable=True),
    WhatsAppDeliveryError("whatsapp_http_401"), WhatsAppDeliveryError("whatsapp_delivery_unknown", uncertain=True),
    RuntimeError("SECRET customer text")])
def test_send_failure_preserves_contact_and_never_retries_duplicate(wa_client, db, monkeypatch, caplog, error):
    calls = []
    def fail(*_):
        calls.append(True)
        raise error
    monkeypatch.setattr(human, "send_text", fail)
    with caplog.at_level(logging.INFO):
        assert post_event(wa_client, payload()).status_code == 200
        assert post_event(wa_client, payload()).status_code == 200
        assert post_event(wa_client, payload(message_id="wamid.later")).status_code == 200
    assert len(calls) == 1
    assert db.query(Message).filter_by(sender="customer").count() == 2
    assert db.query(Conversation).one().status == "HUMAN"
    assert db.query(Message).filter_by(sender="assistant").one().extra_data["delivery_status"] in {"failed", "uncertain"}
    assert "SECRET" not in caplog.text


@pytest.mark.parametrize("echo", ["from_me", "is_echo", "echo", "business_number", "configured_number", "smb_message_echoes", "statuses"])
def test_outgoing_echoes_and_statuses_never_trigger_reply(wa_client, db, monkeypatch, echo):
    monkeypatch.setattr(human, "send_text", lambda *_: pytest.fail("Company echo must not send"))
    data = payload()
    change = data["entry"][0]["changes"][0]
    value = change["value"]
    if echo in {"from_me", "is_echo", "echo"}:
        value["messages"][0][echo] = True
    elif echo == "business_number":
        value["metadata"]["display_phone_number"] = "+55 999 8888-7777"
    elif echo == "configured_number":
        monkeypatch.setattr(settings, "WHATSAPP_BUSINESS_PHONE_NUMBER", "5599988887777")
    elif echo == "smb_message_echoes":
        change["field"] = "smb_message_echoes"
    else:
        value.pop("messages")
        value["statuses"] = [{"id": "wamid.out", "status": "sent"}]
    assert post_event(wa_client, data).status_code == 200
    assert db.query(Message).count() == 0
    assert db.query(Customer).count() == 0


def test_batch_persists_all_messages_before_greeting(wa_client, db, monkeypatch):
    data = payload()
    messages = data["entry"][0]["changes"][0]["value"]["messages"]
    messages.append({**messages[0], "id": "wamid.second"})
    def send(*_):
        assert not db.in_transaction()
        assert db.query(Message).filter_by(sender="customer").count() == 2
        assert db.query(Conversation).one().status == "HUMAN"
        db.rollback()
        return "wamid.sent"
    monkeypatch.setattr(human, "send_text", send)
    assert post_event(wa_client, data).status_code == 200
    assert db.query(Message).filter_by(sender="assistant").count() == 1
    assert db.query(Message).filter_by(sender="assistant").one().extra_data["delivery_status"] == "sent"


def test_different_contacts_each_receive_one_greeting(wa_client, db, monkeypatch):
    sent = []
    monkeypatch.setattr(human, "send_text", lambda recipient, _: sent.append(recipient) or "wamid.sent")
    first = payload()
    second = payload(message_id="wamid.other")
    second["entry"][0]["changes"][0]["value"]["messages"][0]["from"] = "551199998888"
    for data in [first, second, first, second]:
        assert post_event(wa_client, data).status_code == 200
    assert len(sent) == 2
    assert db.query(Conversation).count() == 2


def test_admin_cannot_reenable_whatsapp_ai(wa_client, db):
    assert post_event(wa_client, payload()).status_code == 200
    conversation = db.query(Conversation).one()
    for status in ["AI", "WAITING_HUMAN"]:
        with pytest.raises(SupportError):
            conversation_service.change_status(db, conversation.id, status)
    assert conversation_service.change_status(db, conversation.id, "HUMAN")["status"] == "HUMAN"


def test_old_queue_is_not_processed_and_old_human_conversation_gets_no_welcome(wa_client, db, monkeypatch):
    from services.customer_service import resolve_whatsapp
    conversation = resolve_whatsapp(db, "1234567:5599988887777")
    db.add(Message(conversation_id=conversation.id, sender="customer", content="Contato anterior"))
    db.add(DeliveryJob(kind="inbound", external_id="old-event", routing_key="1234567:5599988887777", payload={}))
    db.commit()
    monkeypatch.setattr(human, "send_text", lambda *_: pytest.fail("Existing conversation must not restart greeting"))
    monkeypatch.setattr(delivery_service, "claim_next", lambda *_: pytest.fail("No old AI queue consumption"))
    assert not delivery_service.run_once()
    assert post_event(wa_client, payload()).status_code == 200
    db.expire_all()
    assert db.query(Conversation).one().status == "HUMAN"
    assert db.query(DeliveryJob).one().status == "cancelled"


def test_late_webhook_is_stored_without_out_of_window_send(wa_client, db, monkeypatch):
    data = payload()
    data["entry"][0]["changes"][0]["value"]["messages"][0]["timestamp"] = str(int((datetime.now(timezone.utc) - timedelta(hours=25)).timestamp()))
    monkeypatch.setattr(human, "send_text", lambda *_: pytest.fail("Reply window expired"))
    assert post_event(wa_client, data).status_code == 200
    assert db.query(Message).filter_by(sender="customer").count() == 1
    assert db.query(Message).filter_by(sender="assistant").one().extra_data["delivery_status"] == "cancelled"


def test_crash_after_reservation_does_not_retry_send(db, monkeypatch):
    from test_whatsapp import incoming
    reserved = human.persist_messages(db, [incoming()])
    assert len(reserved) == 1
    # Simulate process termination before sending: reservation is already durable.
    assert human.persist_messages(db, [incoming()]) == []
    assert db.query(Message).filter_by(sender="customer").count() == 1
    assert db.query(Message).filter_by(sender="assistant").one().extra_data["delivery_status"] == "sending"


def test_database_failure_after_send_keeps_durable_message_and_reservation(db, monkeypatch, caplog):
    from test_whatsapp import incoming
    reserved = human.persist_messages(db, [incoming()])
    execute = db.execute
    def offline(*args, **kwargs):
        raise RuntimeError("PRIVATE database exception")
    monkeypatch.setattr(db, "execute", offline)
    sent = []
    human.send_greetings(db, reserved, sender=lambda *_: sent.append(1) or "wamid.sent")
    monkeypatch.setattr(db, "execute", execute)
    assert human.persist_messages(db, [incoming()]) == []
    assert len(sent) == 1
    assert db.query(Message).filter_by(sender="customer").count() == 1
    assert "whatsapp_greeting_result_unrecorded" in caplog.text
    assert "PRIVATE" not in caplog.text
