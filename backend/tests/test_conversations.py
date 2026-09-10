from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from core.config import settings
from models.atendimento import ChannelIdentity, Conversation, Customer, DeliveryJob, Message, utc_now
from schemas.atendimento import AgentResponse
from services import ai_agent, conversation_service as service, customer_service
from services.customer_service import SupportError


def web(db):
    session = customer_service.create_web_session(db)
    return customer_service.authenticate_web(db, session.session_id)


def test_identity_is_separate_from_customer_and_channel(db):
    one = web(db)
    other = customer_service.resolve_whatsapp(db, "123456:5511999999999")
    assert one.customer_id != other.customer_id
    assert customer_service.resolve_whatsapp(db, "123456:5511999999999").id == other.id
    assert customer_service.resolve_whatsapp(db, "654321:5511999999999").id != other.id
    with pytest.raises(SupportError):
        customer_service.resolve_whatsapp(db, "pretend-verified")


def test_message_is_idempotent_and_reused_id_cannot_change_content(db, monkeypatch):
    conversation = web(db)
    calls = []
    def respond(session, incoming):
        assert not session.in_transaction()
        calls.append(incoming)
        return AgentResponse(message="Olá!", context={"filters": {"size": "M"}})
    monkeypatch.setattr(ai_agent, "respond", respond)
    message_id = str(uuid4())
    first = service.receive(db, conversation, message_id, "oi")
    second = service.receive(db, db.get(Conversation, conversation.id), message_id, "oi")
    assert first == second
    assert len(calls) == 1
    assert db.query(Message).count() == 2
    assert db.get(Conversation, conversation.id).context == {"filters": {"size": "M"}}
    assert "context" not in first.model_dump()
    with pytest.raises(SupportError) as error:
        service.receive(db, conversation, message_id, "texto diferente")
    assert error.value.status_code == 409


def test_two_channels_use_same_agent_and_recent_memory_is_bounded(db, monkeypatch):
    monkeypatch.setattr(settings, "CHAT_HISTORY_MESSAGES", 2)
    seen = []
    def respond(session, incoming):
        seen.append(incoming)
        return AgentResponse(message="Recebido", context={"size": "M"})
    monkeypatch.setattr(ai_agent, "respond", respond)
    conversation = web(db)
    for text in ["camiseta", "tamanho M", "E preta?"]:
        service.receive(db, conversation, str(uuid4()), text)
    service.receive_whatsapp(db, "123456:5511999999999", "wamid.test", "camiseta")
    assert len(seen[-2].history) == 2
    assert seen[-2].context == {"size": "M"}
    assert seen[-2].channel == "web" and seen[-1].channel == "whatsapp"
    assert seen[-1].history == []


def test_handoff_suppresses_automation_and_can_resume(db, monkeypatch):
    conversation = web(db)
    monkeypatch.setattr(ai_agent, "respond", lambda *_: AgentResponse(message="Pedido registrado.", type="handoff", handoff=True))
    first = service.receive(db, conversation, str(uuid4()), "quero atendente")
    assert first.status == "WAITING_HUMAN"
    monkeypatch.setattr(ai_agent, "respond", lambda *_: pytest.fail("LLM must not run during human support"))
    assert service.receive(db, conversation, str(uuid4()), "oi?").type == "silent"
    service.change_status(db, conversation.id, "HUMAN")
    reply = service.receive(db, conversation, str(uuid4()), "preciso de ajuda")
    assert reply.status == "HUMAN" and reply.message == ""
    assert db.query(Message).filter_by(sender="customer").count() == 3
    service.change_status(db, conversation.id, "AI")
    monkeypatch.setattr(ai_agent, "respond", lambda *_: AgentResponse(message="Olá!"))
    assert service.receive(db, conversation, str(uuid4()), "olá").message == "Olá!"


def test_human_takeover_during_model_call_discards_late_response(db, monkeypatch):
    conversation = web(db)
    def takeover(session, incoming):
        service.change_status(session, incoming.conversation_id, "HUMAN")
        return AgentResponse(message="Resposta atrasada")
    monkeypatch.setattr(ai_agent, "respond", takeover)
    reply = service.receive(db, conversation, str(uuid4()), "camiseta")
    assert reply.type == "silent" and reply.status == "HUMAN"
    assert db.query(Message).filter_by(sender="assistant").count() == 0


def test_repeated_failures_handoff_without_leaking_error(db, monkeypatch, caplog):
    conversation = web(db)
    def broken(*_):
        raise RuntimeError("SECRET-and-customer-text")
    monkeypatch.setattr(ai_agent, "respond", broken)
    first = service.receive(db, conversation, str(uuid4()), "oi")
    second = service.receive(db, conversation, str(uuid4()), "de novo")
    assert first.type == "error"
    assert second.type == "handoff" and second.status == "WAITING_HUMAN"
    assert "SECRET-and-customer-text" not in caplog.text
    assert "SECRET-and-customer-text" not in first.model_dump_json()


def test_conversation_lease_rejects_concurrent_message_and_recovers(db, monkeypatch):
    conversation = web(db)
    conversation.processing_token = str(uuid4())
    conversation.processing_until = utc_now() + timedelta(seconds=100)
    db.commit()
    monkeypatch.setattr(ai_agent, "respond", lambda *_: AgentResponse(message="Recuperado"))
    with pytest.raises(SupportError) as error:
        service.receive(db, conversation, str(uuid4()), "oi")
    assert error.value.status_code == 409
    assert db.query(Message).count() == 0
    conversation.processing_until = utc_now() - timedelta(seconds=1)
    db.commit()
    reply = service.receive(db, conversation, str(uuid4()), "oi")
    assert reply.message == "Recuperado"
    assert db.get(Conversation, conversation.id).processing_token is None


def test_web_session_stores_only_hash_expires_and_deletes_owned_data(db):
    session = customer_service.create_web_session(db)
    conversation = customer_service.authenticate_web(db, session.session_id)
    identity = db.get(ChannelIdentity, conversation.identity_id)
    assert identity.external_id != session.session_id and len(identity.external_id) == 64
    identity.expires_at = utc_now() - timedelta(seconds=1)
    db.commit()
    with pytest.raises(SupportError):
        customer_service.authenticate_web(db, session.session_id)
    other = web(db)
    other_id = other.id
    db.add(Message(conversation_id=conversation.id, sender="customer", content="delete me"))
    db.commit()
    deleted_id = conversation.id
    customer_service.delete_web_session(db, conversation)
    db.expire_all()
    assert db.get(Conversation, deleted_id) is None
    assert db.get(Conversation, other_id) is not None
    assert db.query(Message).count() == 0
    assert db.query(Customer).count() == 1


def test_purge_removes_expired_web_and_preserves_active_whatsapp(db):
    conversation = web(db)
    identity = db.get(ChannelIdentity, conversation.identity_id)
    identity.expires_at = utc_now() - timedelta(seconds=1)
    whatsapp = customer_service.resolve_whatsapp(db, "123456:5511999999999")
    db.commit()
    service.purge_expired(db)
    assert db.query(Conversation).count() == 1
    assert db.query(Conversation).one().id == whatsapp.id
    assert db.query(Customer).count() == 1


def test_database_rejects_arbitrary_status_and_sender(db):
    conversation = web(db)
    conversation.status = "invented"
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(Message(conversation_id=conversation.id, sender="unknown", content="test"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
