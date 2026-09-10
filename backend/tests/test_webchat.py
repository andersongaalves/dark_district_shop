import logging
from uuid import uuid4

import pytest

from core.config import settings
from core.request_security import LoginRateLimiter
from core.support_logging import WebhookAccessFilter
from main import app
from models.atendimento import Conversation
from schemas.atendimento import AgentResponse
from services import ai_agent


def session(client):
    response = client.post("/api/chat/sessions")
    assert response.status_code == 201
    return response.json()


def headers(data):
    return {"Authorization": f"Bearer {data['session_id']}"}


def test_web_api_conversation_history_and_isolation(public_client):
    one, two = session(public_client), session(public_client)
    response = public_client.post("/api/chat/messages", headers=headers(one), json={"message_id": str(uuid4()), "message": "oi"})
    assert response.status_code == 200
    assert response.json()["conversation_id"] == one["conversation_id"]
    assert "context" not in response.json()
    assert response.headers["cache-control"] == "no-store"
    history = public_client.get("/api/chat/messages", headers=headers(one)).json()
    assert len(history["messages"]) == 2
    assert history["messages"][0]["external_id"] == response.json()["message_id"]
    assert public_client.get("/api/chat/messages", headers=headers(two)).json()["messages"] == []
    assert public_client.get("/api/chat/messages", headers={"Authorization": f"Bearer {one['conversation_id']}"}).status_code == 401
    assert public_client.post("/api/chat/messages", headers=headers(two), json={"message_id": str(uuid4()), "message": "oi", "conversation_id": one["conversation_id"]}).status_code == 422


@pytest.mark.parametrize("credential", [None, "", "x" * 43, "x" * 5000, "admin-token"])
def test_unknown_session_cannot_read_or_write(public_client, credential):
    auth = {"Authorization": f"Bearer {credential}"} if credential is not None else {}
    assert public_client.get("/api/chat/messages", headers=auth).status_code == 401
    assert public_client.post("/api/chat/messages", headers=auth, json={"message_id": str(uuid4()), "message": "oi"}).status_code == 401


@pytest.mark.parametrize("payload", [{"message_id": "invalid", "message": "oi"}, {"message_id": str(uuid4()), "message": " "},
    {"message_id": str(uuid4()), "message": "x" * 2001}, {"message_id": str(uuid4()), "message": "a\u0000b"}])
def test_invalid_input_is_rejected_before_agent(public_client, payload, monkeypatch):
    monkeypatch.setattr(ai_agent, "respond", lambda *_: pytest.fail("invalid input reached agent"))
    assert public_client.post("/api/chat/messages", headers=headers(session(public_client)), json=payload).status_code == 422


def test_rate_limits_creation_body_session_and_no_store(public_client, monkeypatch):
    one = session(public_client)
    monkeypatch.setattr(app.state, "chat_creation_limiter", LoginRateLimiter(attempts=1, window_seconds=3600))
    session(public_client)
    result = public_client.post("/api/chat/sessions")
    assert result.status_code == 429 and result.headers["retry-after"]
    assert result.headers["cache-control"] == "no-store"
    assert public_client.post("/api/chat/messages", headers=headers(one), content="x" * 16385).status_code == 413
    monkeypatch.setattr(app.state, "chat_session_limiter", LoginRateLimiter(attempts=1, window_seconds=60))
    payload = {"message_id": str(uuid4()), "message": "oi"}
    assert public_client.post("/api/chat/messages", headers=headers(one), json=payload).status_code == 200
    assert public_client.post("/api/chat/messages", headers=headers(one), json=payload).status_code == 429


def test_global_limit_and_session_message_budget(public_client, monkeypatch):
    one = session(public_client)
    monkeypatch.setattr(settings, "CHAT_MAX_MESSAGES_PER_SESSION", 1)
    for expected in (200, 429):
        assert public_client.post("/api/chat/messages", headers=headers(one), json={"message_id": str(uuid4()), "message": "oi"}).status_code == expected
    monkeypatch.setattr(app.state, "chat_global_limiter", LoginRateLimiter(attempts=1, window_seconds=60))
    assert public_client.post("/api/chat/sessions").status_code == 201
    assert public_client.post("/api/chat/sessions").status_code == 429


def test_session_delete_revokes_credential_and_feature_can_be_disabled(public_client, monkeypatch):
    one = session(public_client)
    assert public_client.delete("/api/chat/session", headers=headers(one)).status_code == 204
    assert public_client.get("/api/chat/messages", headers=headers(one)).status_code == 401
    monkeypatch.setattr(settings, "CHAT_ENABLED", False)
    assert public_client.post("/api/chat/sessions").status_code == 503
    assert public_client.get("/produtos").status_code == 200


def test_admin_conversations_require_admin_and_control_handoff(public_client, client, db):
    one = session(client)
    path = f"/admin/conversations/{one['conversation_id']}"
    assert client.patch(path, json={"status": "HUMAN"}).status_code == 200
    assert client.get("/admin/conversations?status=HUMAN").json()[0]["conversation_id"] == one["conversation_id"]
    assert client.get(path + "/messages").status_code == 200
    response = client.post("/api/chat/messages", headers=headers(one), json={"message_id": str(uuid4()), "message": "oi"})
    assert response.json()["type"] == "silent"
    from core.security import get_current_user
    app.dependency_overrides.pop(get_current_user)
    assert public_client.get("/admin/conversations").status_code == 401
    assert public_client.patch(path, headers=headers(one), json={"status": "AI"}).status_code == 401


def test_meta_verification_token_is_removed_from_access_log_arguments():
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 1, '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1", "GET", "/webhooks/whatsapp?hub.verify_token=secret&hub.challenge=123", "1.1", 200), None)
    assert WebhookAccessFilter().filter(record)
    assert "secret" not in record.getMessage() and "hub.challenge" not in record.getMessage()


def test_web_api_catalog_response_is_persisted_with_current_price_and_variant(client, db):
    from datetime import timedelta
    from models.atendimento import utc_now
    from models.produto import Produto
    from test_catalog_tools import create_product
    create_product(client, price=100, is_offer=True, offer_price=60,
        offer_ends_at=(utc_now() + timedelta(hours=1)).isoformat(),
        variants=[{"size": "M", "color": "Preto", "quantity": 2}])
    visitor = session(client)
    first = client.post("/api/chat/messages", headers=headers(visitor),
        json={"message_id": str(uuid4()), "message": "Tem camiseta preta M até R$80?"})
    assert first.status_code == 200, first.text
    result = first.json()
    assert result["type"] == "product_results" and result["products"][0]["effective_price"] == 60
    assert "M / Preto: 2 un." in result["message"]
    product = db.get(Produto, "prod-001")
    product.offer_ends_at = utc_now() - timedelta(seconds=1)
    db.commit()
    second = client.post("/api/chat/messages", headers=headers(visitor),
        json={"message_id": str(uuid4()), "message": "Qual o preço dessa?"})
    assert second.json()["products"][0]["effective_price"] == 100
    history = client.get("/api/chat/messages", headers=headers(visitor)).json()
    assert history["messages"][-1]["response"]["products"][0]["effective_price"] == 100
