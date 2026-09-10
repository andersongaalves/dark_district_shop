import os
import secrets
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Always isolate tests from local credentials and databases.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = secrets.token_urlsafe(32)
# External integrations are opt-in in tests regardless of the operator's environment.
os.environ["LLM_PROVIDER"] = "disabled"
os.environ["WHATSAPP_ENABLED"] = "false"
os.environ["LLM_API_KEY"] = ""
os.environ["WHATSAPP_ACCESS_TOKEN"] = ""
os.environ["META_APP_SECRET"] = ""
os.environ["WHATSAPP_VERIFY_TOKEN"] = ""

from database import Base, get_db
from main import app
from core.security import get_current_user
from core.request_security import LoginRateLimiter
from core.config import settings
from models.usuario import Usuario


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def public_client(db, monkeypatch):
    monkeypatch.setattr(settings, "CHAT_ENABLED", True)
    for name, attempts, window in [
        ("chat_ip_limiter", 60, 60), ("chat_creation_limiter", 10, 3600),
        ("chat_session_limiter", 15, 60), ("chat_global_limiter", 120, 60),
    ]:
        monkeypatch.setattr(app.state, name, LoginRateLimiter(attempts=attempts, window_seconds=window))
    monkeypatch.setattr(app.state, "login_limiter", LoginRateLimiter(
        attempts=settings.LOGIN_ATTEMPTS, window_seconds=settings.LOGIN_WINDOW_SECONDS
    ))
    def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def client(public_client, db):
    usuario = Usuario(username="usuario_teste", password_hash="unused-test-hash", active=True)
    db.add(usuario)
    db.commit()
    app.dependency_overrides[get_current_user] = lambda: usuario
    return public_client
