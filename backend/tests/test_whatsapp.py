from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import event, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker

from channels.whatsapp_channel import IncomingText, render_text
from core.config import settings
from database import get_db
from integrations.whatsapp.client import WhatsAppDeliveryError, send_text
from models.atendimento import ChannelIdentity, Conversation, Customer, DeliveryJob
from models.produto import Produto
from routers.whatsapp import router
from schemas.atendimento import AgentResponse, ChatReply
from services import delivery_service as delivery
from test_produtos import produto_payload
from tools.catalog_tools import serialize_product


@pytest.fixture(autouse=True)
def whatsapp_settings(monkeypatch):
    for name, value in {
        "WHATSAPP_ENABLED": True, "WHATSAPP_VERIFY_TOKEN": SecretStr("test-verification"),
        "META_APP_SECRET": SecretStr("test-signing-secret"),
        "WHATSAPP_ACCESS_TOKEN": SecretStr("test-access-token"),
        "WHATSAPP_PHONE_NUMBER_ID": "1234567", "WHATSAPP_WABA_ID": "7654321",
        "WHATSAPP_GRAPH_VERSION": "v23.0",
    }.items():
        monkeypatch.setattr(settings, name, value)


@pytest.fixture
def wa_client(db):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        yield client


@pytest.fixture
def sessions(db):
    return sessionmaker(bind=db.get_bind(), autoflush=False)


@pytest.fixture
def conversation(db):
    customer = Customer()
    db.add(customer)
    db.flush()
    identity = ChannelIdentity(customer_id=customer.id, channel="whatsapp", external_id="1234567:5599988887777")
    db.add(identity)
    db.flush()
    result = Conversation(customer_id=customer.id, identity_id=identity.id, channel="whatsapp")
    db.add(result)
    db.commit()
    db.refresh(result)
    return result


def payload(*, message_id="wamid.test", text="Tem cropped preto M?"):
    return {"object": "whatsapp_business_account", "entry": [{"id": "7654321", "changes": [{
        "field": "messages", "value": {"messaging_product": "whatsapp", "metadata": {"phone_number_id": "1234567"},
        "messages": [{"from": "5599988887777", "id": message_id, "timestamp": str(int(datetime.now(timezone.utc).timestamp())),
                      "type": "text", "text": {"body": text}}]},
    }]}]}


def post_event(client, event):
    body = event if isinstance(event, bytes) else json.dumps(event, ensure_ascii=False, indent=2).encode()
    signature = "sha256=" + hmac.new(b"test-signing-secret", body, hashlib.sha256).hexdigest()
    return client.post("/webhooks/whatsapp", content=body,
                       headers={"x-hub-signature-256": signature, "content-type": "application/json"})


def test_verification_challenge_is_plaintext_and_secret_is_required(wa_client):
    params = {"hub.mode": "subscribe", "hub.verify_token": "test-verification", "hub.challenge": "123456"}
    result = wa_client.get("/webhooks/whatsapp", params=params)
    assert result.status_code == 200 and result.text == "123456"
    assert result.headers["content-type"].startswith("text/plain")
    params["hub.verify_token"] = "wrong"
    assert wa_client.get("/webhooks/whatsapp", params=params).status_code == 403


def test_disabled_whatsapp_does_not_accept_events(wa_client, monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", False)
    assert post_event(wa_client, payload()).status_code == 503


def test_webhook_persists_and_deduplicates_before_worker(wa_client, db):
    event = payload()
    assert post_event(wa_client, event).status_code == 200
    assert post_event(wa_client, event).status_code == 200
    jobs = db.scalars(select(DeliveryJob)).all()
    assert len(jobs) == 1
    assert jobs[0].status == "pending" and jobs[0].attempts == 0
    assert jobs[0].payload["text"] == "Tem cropped preto M?"
    assert db.scalars(select(Conversation)).all() == []


def test_raw_body_signature_cannot_be_reused_after_tampering(wa_client, db):
    body = json.dumps(payload()).encode()
    signature = "sha256=" + hmac.new(b"test-signing-secret", body, hashlib.sha256).hexdigest()
    response = wa_client.post("/webhooks/whatsapp", content=body + b" ", headers={"x-hub-signature-256": signature})
    assert response.status_code == 403
    assert db.scalars(select(DeliveryJob)).all() == []


@pytest.mark.parametrize("target", ["account", "phone"])
def test_signed_wrong_account_or_number_is_rejected(wa_client, target):
    event = payload()
    if target == "account":
        event["entry"][0]["id"] = "9999"
    else:
        event["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"] = "9999"
    assert post_event(wa_client, event).status_code == 403


@pytest.mark.parametrize("event", [b"{", [], {"object": "other"}, {"object": "whatsapp_business_account", "entry": 5}])
def test_signed_malformed_payload_is_rejected(wa_client, event):
    assert post_event(wa_client, event).status_code == 400


def test_delivery_receipts_and_media_do_not_become_agent_messages(wa_client, db):
    event = payload()
    value = event["entry"][0]["changes"][0]["value"]
    value["messages"][0]["type"] = "image"
    value["statuses"] = [{"id": "wamid.out", "status": "delivered"}]
    assert post_event(wa_client, event).status_code == 200
    assert db.scalars(select(DeliveryJob)).all() == []


def test_oversized_message_rejects_entire_batch(wa_client, db):
    event = payload(text="x" * (settings.CHAT_MAX_MESSAGE_LENGTH + 1))
    assert post_event(wa_client, event).status_code == 400
    assert db.scalars(select(DeliveryJob)).all() == []


def incoming():
    return IncomingText("1234567", "5599988887777", "wamid.test", "Olá", int(datetime.now(timezone.utc).timestamp()))


def test_worker_uses_shared_service_then_persistent_outbox_without_open_send_transaction(db, sessions, conversation):
    conversation_id = conversation.id
    delivery.enqueue_inbound(db, [incoming()])
    observed = []

    def receive(session, **kwargs):
        assert kwargs == {"external_id": "1234567:5599988887777", "message_id": "wamid.test", "text": "Olá"}
        observed.append("agent")
        return ChatReply(conversation_id=conversation_id, status="AI", message_id="reply-1", message="Oi! Como posso ajudar?")

    assert delivery.run_once(session_factory=sessions, receiver=receive)
    db.expire_all()
    jobs = db.scalars(select(DeliveryJob).order_by(DeliveryJob.created_at)).all()
    assert [job.status for job in jobs] == ["sent", "pending"]
    assert jobs[1].source_message_id == "reply-1"
    db.rollback()
    active = set()
    engine = db.get_bind()
    def begin(connection):
        active.add(id(connection))
    def finish(connection):
        active.discard(id(connection))
    event.listen(engine, "begin", begin)
    event.listen(engine, "commit", finish)
    event.listen(engine, "rollback", finish)
    try:
        def send(recipient, body):
            assert not active
            assert recipient == "5599988887777" and "Como posso ajudar" in body
            observed.append("send")
            return "wamid.sent"
        assert delivery.run_once(session_factory=sessions, receiver=receive, sender=send)
    finally:
        event.remove(engine, "begin", begin)
        event.remove(engine, "commit", finish)
        event.remove(engine, "rollback", finish)
    assert observed == ["agent", "send"]
    db.expire_all()
    assert db.scalar(select(DeliveryJob).where(DeliveryJob.kind == "outbound")).payload["meta_message_id"] == "wamid.sent"


def add_outbound(db, conversation, *, allow_waiting=False, timestamp=None):
    job = DeliveryJob(kind="outbound", external_id="out:test", conversation_id=conversation.id,
                      routing_key="1234567:5599988887777",
                      payload={"recipient": "5599988887777", "phone_number_id": "1234567", "text": "Resposta",
                               "timestamp": timestamp or int(datetime.now(timezone.utc).timestamp()),
                               "allow_waiting": allow_waiting})
    db.add(job)
    db.commit()
    return job


@pytest.mark.parametrize("status,allow_waiting,expected", [
    ("HUMAN", False, "cancelled"), ("HUMAN", True, "cancelled"),
    ("WAITING_HUMAN", False, "cancelled"), ("WAITING_HUMAN", True, "sent"), ("AI", False, "sent"),
])
def test_worker_rechecks_handoff_state_immediately_before_send(db, sessions, conversation, status, allow_waiting, expected):
    job = add_outbound(db, conversation, allow_waiting=allow_waiting)
    conversation.status = status
    db.commit()
    calls = []
    delivery.run_once(session_factory=sessions, receiver=lambda *_: None,
                      sender=lambda *_: calls.append(True) or "wamid.sent")
    db.refresh(job)
    assert job.status == expected
    assert bool(calls) == (expected == "sent")


def test_old_outbound_is_cancelled_without_contacting_meta(db, sessions, conversation):
    job = add_outbound(db, conversation, timestamp=int((datetime.now(timezone.utc) - timedelta(hours=25)).timestamp()))
    def forbidden(*_):
        pytest.fail("No external call is allowed outside the reply window")
    delivery.run_once(session_factory=sessions, receiver=forbidden, sender=forbidden)
    db.refresh(job)
    assert job.status == "cancelled" and job.error_code == "reply_window_expired"


def test_worker_recovers_inbound_lease_but_quarantines_ambiguous_outbound(db, sessions, conversation):
    outbound = add_outbound(db, conversation)
    outbound.status = "processing"
    outbound.locked_at = datetime.now(timezone.utc) - timedelta(seconds=settings.DELIVERY_LEASE_SECONDS + 5)
    delivery.enqueue_inbound(db, [incoming()])
    inbound = db.scalar(select(DeliveryJob).where(DeliveryJob.kind == "inbound"))
    inbound.status, inbound.locked_at, inbound.attempts = "processing", outbound.locked_at, 1
    db.commit()
    claim = delivery.claim_next(sessions)
    db.refresh(inbound)
    db.refresh(outbound)
    assert claim.id == inbound.id and claim.attempts == 2
    assert outbound.status == "uncertain" and outbound.error_code == "worker_interrupted"


def test_safe_retry_is_bounded_and_unknown_delivery_is_never_retried(db, sessions, conversation):
    job = add_outbound(db, conversation)
    def retry(*_):
        raise WhatsAppDeliveryError("whatsapp_connection", retryable=True)
    for attempt in range(settings.DELIVERY_MAX_ATTEMPTS):
        delivery.run_once(session_factory=sessions, receiver=lambda *_: None, sender=retry)
        db.refresh(job)
        assert job.attempts == attempt + 1
        if attempt + 1 < settings.DELIVERY_MAX_ATTEMPTS:
            assert job.status == "pending"
            job.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
    assert job.status == "failed"
    job.status, job.attempts, job.available_at = "pending", 0, datetime.now(timezone.utc)
    db.commit()
    def uncertain(*_):
        raise WhatsAppDeliveryError("whatsapp_delivery_unknown", uncertain=True)
    delivery.run_once(session_factory=sessions, receiver=lambda *_: None, sender=uncertain)
    db.refresh(job)
    assert job.status == "uncertain"
    assert not delivery.run_once(session_factory=sessions, receiver=lambda *_: None, sender=uncertain)


def test_old_lease_owner_cannot_complete_reclaimed_job(db, sessions):
    delivery.enqueue_inbound(db, [incoming()])
    first = delivery.claim_next(sessions)
    job = db.get(DeliveryJob, first.id)
    job.locked_at = datetime.now(timezone.utc) - timedelta(seconds=settings.DELIVERY_LEASE_SECONDS + 5)
    db.commit()
    second = delivery.claim_next(sessions)
    delivery._finish(first, "sent", session_factory=sessions)
    db.refresh(job)
    assert job.status == "processing" and job.attempts == second.attempts


def test_cloud_api_client_uses_official_endpoint_and_bounded_text():
    def handler(request):
        assert str(request.url) == "https://graph.facebook.com/v23.0/1234567/messages"
        assert request.headers["Authorization"] == "Bearer test-access-token"
        body = json.loads(request.content)
        assert body["to"] == "5599988887777" and body["type"] == "text"
        assert body["text"] == {"preview_url": False, "body": "Oi!"}
        return httpx.Response(200, json={"messages": [{"id": "wamid.sent"}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert send_text("5599988887777", "Oi!", http_client=client) == "wamid.sent"


@pytest.mark.parametrize("status,retryable,uncertain", [(429, True, False), (500, False, True), (401, False, False), (302, False, False)])
def test_cloud_api_errors_are_redacted_and_classified(status, retryable, uncertain):
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(status, json={"error": "SENSITIVE"}))) as client:
        with pytest.raises(WhatsAppDeliveryError) as exc:
            send_text("5599988887777", "Oi", http_client=client)
    assert "SENSITIVE" not in str(exc.value)
    assert (exc.value.retryable, exc.value.uncertain) == (retryable, uncertain)


def test_cloud_api_read_timeout_is_ambiguous():
    def handler(request):
        raise httpx.ReadTimeout("SENSITIVE", request=request)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(WhatsAppDeliveryError) as exc:
            send_text("5599988887777", "Oi", http_client=client)
    assert exc.value.uncertain and "SENSITIVE" not in str(exc.value)


def test_adapter_bounds_whatsapp_message():
    assert len(render_text(AgentResponse(message="x" * 6000))) == 4096


@pytest.mark.parametrize("change", ["offer", "stock", "deleted", "unchanged"])
def test_delayed_outbox_revalidates_commercial_facts_before_sending(client, db, sessions, conversation, change):
    data = {**produto_payload(), "price": 100, "is_offer": True, "offer_price": 60,
            "offer_ends_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}
    assert client.post("/produtos", json=data).status_code == 201
    product = db.get(Produto, data["id"])
    snapshot = serialize_product(product).model_dump(mode="json")
    job = add_outbound(db, conversation)
    job.payload = {**job.payload, "products": [snapshot], "text": "Oferta por R$ 60,00"}
    if change == "offer":
        product.offer_ends_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    elif change == "stock":
        product.available = False
    elif change == "deleted":
        db.delete(product)
    db.commit()
    sent = []
    delivery.run_once(session_factory=sessions, receiver=lambda *_: None,
                      sender=lambda recipient, body: sent.append(body) or "wamid.sent")
    assert len(sent) == 1
    if change == "unchanged":
        assert sent[0] == "Oferta por R$ 60,00"
    else:
        assert "catálogo mudou" in sent[0] and "60,00" not in sent[0]


def test_claim_serializes_identity_and_retry_does_not_let_later_messages_overtake(db, sessions):
    first = incoming()
    second = IncomingText(first.phone_number_id, first.sender, "wamid.next", "E preta?", first.timestamp)
    other = IncomingText(first.phone_number_id, "551188887777", "wamid.other", "Oi", first.timestamp)
    delivery.enqueue_inbound(db, [first, second, other])
    initial = delivery.claim_next(sessions)
    assert initial.payload["message_id"] == first.message_id
    # The competing worker is allowed to process another person, never the next
    # message of the conversation whose first message is still processing.
    competing = delivery.claim_next(sessions)
    assert competing.payload["message_id"] == other.message_id
    assert delivery.claim_next(sessions) is None
    delivery._finish(initial, "pending", session_factory=sessions)
    assert delivery.claim_next(sessions) is None
    db.expire_all()
    job = db.get(DeliveryJob, initial.id)
    job.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    retried = delivery.claim_next(sessions)
    assert retried.id == initial.id and retried.attempts == 2
    delivery._finish(retried, "sent", session_factory=sessions)
    next_job = delivery.claim_next(sessions)
    assert next_job.payload["message_id"] == second.message_id


def test_delivery_order_query_compiles_to_postgres_row_locks():
    sql = str(delivery.ready_jobs_query(datetime.now(timezone.utc)).compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "NOT (EXISTS" in sql and "routing_key" in sql
