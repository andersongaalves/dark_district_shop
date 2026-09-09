import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from pydantic import ValidationError

from core.config import Settings, settings
from core.request_security import LoginRateLimiter, RequestSecurityMiddleware
from core.security import DUMMY_HASH, hash_password, verify_password
from main import app
from schemas.produto import ProdutoCreate, ProdutoUpdate, ProdutoImagemCreate, ProdutoVarianteCreate
from test_auth import criar_usuario
from test_produtos import produto_payload


@pytest.mark.parametrize("claims", [
    {"sub": "admin"}, {"sub": "admin", "exp": None},
    {"sub": "admin", "exp": []}, {"sub": "admin", "exp": {}},
    {"sub": "admin", "exp": "9999999999"},
    {"sub": "admin", "exp": float("inf")},
    {"sub": "", "exp": 9_999_999_999},
    {"sub": ["admin"], "exp": 9_999_999_999},
])
def test_tokens_require_valid_expiration_and_subject(public_client, db, claims):
    criar_usuario(db)
    token = jwt.encode(claims, settings.SECRET_KEY.get_secret_value(), algorithm=settings.ALGORITHM)
    response = public_client.post("/produtos", json=produto_payload(),
                                  headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_other_signing_algorithms_are_rejected(public_client, db):
    criar_usuario(db)
    token = jwt.encode({"sub": "admin", "exp": 9_999_999_999},
                       settings.SECRET_KEY.get_secret_value(), algorithm="HS512")
    response = public_client.post("/produtos", json=produto_payload(),
                                  headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_oversized_token_is_rejected_before_decoding(public_client, monkeypatch):
    def unexpected_decode(*_args, **_kwargs):
        pytest.fail("An oversized token must not reach the JWT parser")
    monkeypatch.setattr("core.security.jwt.decode", unexpected_decode)
    response = public_client.delete("/produtos/item", headers={"Authorization": "Bearer " + "a" * 4097})
    assert response.status_code == 401


@pytest.mark.parametrize("password", ["a" * 73, "á" * 37, "invalid\x00password"])
def test_invalid_password_input_fails_closed(public_client, db, password):
    criar_usuario(db)
    response = public_client.post("/auth/login", data={"username": "admin", "password": password})
    assert response.status_code == 401
    assert response.json()["detail"] == "Usuário ou senha inválidos."
    with pytest.raises(ValueError):
        hash_password(password)


def test_passwords_cannot_authenticate_by_their_truncated_prefix():
    password_hash = hash_password("a" * 72)
    assert verify_password("a" * 72, password_hash)
    assert not verify_password("a" * 72 + "wrong-suffix", password_hash)


def test_corrupt_stored_hash_does_not_raise_or_authenticate():
    assert not verify_password("password", "not-a-valid-hash")


def test_unknown_account_still_checks_a_hash(public_client, monkeypatch):
    calls = []
    monkeypatch.setattr("routers.auth.verify_password", lambda password, hashed: calls.append(hashed) or False)
    response = public_client.post("/auth/login", data={"username": "missing", "password": "test"})
    assert response.status_code == 401
    assert calls == [DUMMY_HASH]


def test_login_failures_are_indistinguishable(public_client, db):
    criar_usuario(db, username="active")
    criar_usuario(db, username="inactive", active=False)
    responses = [public_client.post("/auth/login", data={"username": username, "password": "wrong"})
                 for username in ["active", "inactive", "missing"]]
    assert all(response.status_code == 401 for response in responses)
    assert len({response.text for response in responses}) == 1
    assert all(response.headers["cache-control"] == "no-store" for response in responses)


def test_successful_login_response_cannot_be_cached(public_client, db):
    criar_usuario(db)
    response = public_client.post("/auth/login", data={"username": "admin", "password": "123456"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


def test_rate_limit_counts_invalid_forms_and_ignores_forged_forwarding_headers(public_client, monkeypatch):
    monkeypatch.setattr(app.state, "login_limiter", LoginRateLimiter(attempts=2))
    for number in range(2):
        response = public_client.post("/auth/login", data={}, headers={"X-Forwarded-For": f"192.0.2.{number}"})
        assert response.status_code == 422
    blocked = public_client.post("/auth/login", data={}, headers={"X-Forwarded-For": "192.0.2.99"})
    assert blocked.status_code == 429
    assert 1 <= int(blocked.headers["retry-after"]) <= 60
    assert blocked.headers["cache-control"] == "no-store"
    assert public_client.get("/produtos").status_code == 200


def test_redirected_login_counts_one_attempt(public_client, monkeypatch):
    monkeypatch.setattr(app.state, "login_limiter", LoginRateLimiter(attempts=1))
    assert public_client.post("/auth/login/", data={}).status_code == 422
    assert public_client.post("/auth/login/", data={}).status_code == 429


def test_root_path_does_not_bypass_login_limit(public_client, monkeypatch):
    monkeypatch.setattr(app.state, "login_limiter", LoginRateLimiter(attempts=1))
    with TestClient(app, root_path="/api") as client:
        assert client.post("/api/auth/login", data={}).status_code == 422
        assert client.post("/api/auth/login", data={}).status_code == 429


def test_rate_limiter_recovers_and_does_not_evict_active_limits():
    now = [0]
    limiter = LoginRateLimiter(attempts=2, window_seconds=60, max_clients=2, clock=lambda: now[0])
    assert limiter.retry_after("one") is None
    assert limiter.retry_after("one") is None
    assert limiter.retry_after("two") is None
    assert limiter.retry_after("one") == 60
    assert limiter.retry_after("three") == 60
    now[0] = 60
    assert limiter.retry_after("three") is None
    assert limiter.retry_after("one") is None


def test_concurrent_attempts_cannot_bypass_the_limit():
    limiter = LoginRateLimiter(attempts=3)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(limiter.retry_after, ["same-client"] * 20))
    assert results.count(None) == 3


def test_login_body_limit_preserves_cors_and_prevents_processing(public_client):
    response = public_client.post("/auth/login", content="x" * (settings.MAX_LOGIN_BODY_BYTES + 1),
                                  headers={"Origin": "http://localhost:5500"})
    assert response.status_code == 413
    assert response.headers["access-control-allow-origin"] == "http://localhost:5500"
    assert response.headers["cache-control"] == "no-store"


def test_general_body_limit_is_applied_before_json_parsing(public_client):
    response = public_client.post("/produtos", content="x" * (settings.MAX_REQUEST_BODY_BYTES + 1),
                                  headers={"Content-Type": "application/json"})
    assert response.status_code == 413


@pytest.mark.parametrize("declared_length", [None, b"1"])
def test_chunked_or_underreported_body_cannot_bypass_size_limit(declared_length):
    async def run():
        messages = []
        chunks = iter([
            {"type": "http.request", "body": b"a" * 6, "more_body": True},
            {"type": "http.request", "body": b"b" * 6, "more_body": False},
        ])
        async def receive():
            return next(chunks)
        async def send(message):
            messages.append(message)
        async def downstream(*_args):
            pytest.fail("Oversized body reached the application")
        middleware = RequestSecurityMiddleware(downstream, max_body_bytes=10, max_login_body_bytes=10)
        scope = {"type": "http", "method": "POST", "path": "/produtos",
                 "headers": [] if declared_length is None else [(b"content-length", declared_length)]}
        await middleware(scope, receive, send)
        assert messages[0]["status"] == 413
    asyncio.run(run())


def test_secret_configuration_masks_values_and_validation_errors():
    secret = "sensitive-test-value-" * 3
    database = "postgresql://test:private-value@localhost/test"
    config = Settings(_env_file=None, SECRET_KEY=secret, DATABASE_URL=database)
    assert secret not in repr(config)
    assert database not in repr(config)
    assert secret not in config.model_dump_json()
    assert database not in config.model_dump_json()
    with pytest.raises(ValidationError) as failure:
        Settings(_env_file=None, SECRET_KEY=secret, DATABASE_URL=database, LOGIN_ATTEMPTS="invalid")
    assert secret not in str(failure.value)
    assert database not in str(failure.value)


def test_weak_key_warns_without_disclosing_or_replacing_it():
    with pytest.warns(RuntimeWarning, match="SECRET_KEY") as warnings:
        config = Settings(_env_file=None, DATABASE_URL="sqlite://", SECRET_KEY="weak-test-key")
    assert config.SECRET_KEY.get_secret_value() == "weak-test-key"
    assert "weak-test-key" not in str(warnings[0].message)


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_nonfinite_prices_cannot_poison_the_product_listing(value):
    with pytest.raises(ValidationError):
        ProdutoCreate(**{**produto_payload(), "price": value})
    with pytest.raises(ValidationError):
        ProdutoUpdate(price=value)


@pytest.mark.parametrize("field,limit", [("id", 50), ("title", 200), ("category", 100), ("gender", 50)])
def test_product_strings_respect_database_limits(field, limit):
    with pytest.raises(ValidationError):
        ProdutoCreate(**{**produto_payload(), field: "x" * (limit + 1)})


def test_relation_inputs_respect_database_limits():
    with pytest.raises(ValidationError):
        ProdutoVarianteCreate(quantity=2**31)
    with pytest.raises(ValidationError):
        ProdutoVarianteCreate(size="x" * 51)
    with pytest.raises(ValidationError):
        ProdutoImagemCreate(url="x" * 501)
    with pytest.raises(ValidationError):
        ProdutoImagemCreate(url="https://example.com/image.jpg", ordem=2**31)
