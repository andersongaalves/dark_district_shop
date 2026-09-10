from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from test_produtos import produto_payload
from models import produto as product_model
from services import produtos as product_service


@pytest.fixture
def offer_clock(monkeypatch):
    class Clock(datetime):
        current = datetime(2030, 1, 2, 15, 0, tzinfo=timezone.utc)

        @classmethod
        def now(cls, tz=None):
            return cls.current.astimezone(tz) if tz else cls.current.replace(tzinfo=None)

    monkeypatch.setattr(product_model, "datetime", Clock)
    monkeypatch.setattr(product_service, "datetime", Clock)
    return Clock


def create_offer(client, offer_clock, **overrides):
    return client.post("/produtos", json={**produto_payload(), "price": 100, "is_offer": True,
        "offer_price": 70, "offer_ends_at": (offer_clock.current + timedelta(hours=1)).isoformat(), **overrides})


def test_offer_expires_exactly_at_deadline_without_modifying_original_price(client, offer_clock):
    created = create_offer(client, offer_clock)
    assert created.status_code == 201
    assert created.json()["price"] == 100
    assert created.json()["effective_price"] == 70
    assert created.json()["offer_active"] is True
    offer_clock.current += timedelta(hours=1)
    expired = client.get("/produtos/prod-001").json()
    assert expired["price"] == 100
    assert expired["offer_price"] == 70
    assert expired["effective_price"] == 100
    assert expired["offer_active"] is False
    assert expired["is_offer"] is True  # Preserve configuration for the ADM.
    assert client.get("/produtos?offer_active=true&available=true").json() == []
    assert len(client.get("/produtos?is_offer=true").json()) == 1
    assert len(client.get("/produtos?offer_active=false").json()) == 1


def test_discount_can_be_disabled_and_deadline_is_optional(client, offer_clock):
    created = create_offer(client, offer_clock, offer_ends_at=None).json()
    assert created["effective_price"] == 70
    assert client.put("/produtos/prod-001", json={"is_offer": False}).json()["effective_price"] == 100
    assert client.put("/produtos/prod-001", json={"is_offer": True}).json()["effective_price"] == 70
    cleared = client.put("/produtos/prod-001", json={"offer_price": None, "offer_ends_at": None}).json()
    assert cleared["offer_price"] is None and cleared["offer_ends_at"] is None
    assert cleared["effective_price"] == 100


@pytest.mark.parametrize("price", [-1, 100, 101, "NaN", "Infinity"])
def test_invalid_offer_prices_are_rejected(client, offer_clock, price):
    assert create_offer(client, offer_clock, offer_price=price).status_code == 422


def test_partial_updates_validate_merged_prices_and_roll_back(client, offer_clock):
    create_offer(client, offer_clock)
    assert client.put("/produtos/prod-001", json={"price": 60, "title": "Should roll back"}).status_code == 422
    assert client.get("/produtos/prod-001").json()["title"] == produto_payload()["title"]
    updated = client.put("/produtos/prod-001", json={"price": 60, "offer_price": 40})
    assert updated.json()["effective_price"] == 40
    assert updated.json()["price"] == 60


def test_future_deadlines_require_timezone_and_return_utc(client, offer_clock):
    assert create_offer(client, offer_clock, offer_ends_at="2030-01-02T16:00:00").status_code == 422
    assert create_offer(client, offer_clock, offer_ends_at=offer_clock.current.isoformat()).status_code == 422
    response = create_offer(client, offer_clock, offer_ends_at="2030-01-02T13:00:00-03:00")
    assert response.status_code == 201
    assert response.json()["offer_ends_at"] == "2030-01-02T16:00:00Z"


def test_expired_offers_allow_unrelated_edits_and_extension(client, offer_clock):
    created = create_offer(client, offer_clock).json()
    offer_clock.current += timedelta(hours=2)
    response = client.put("/produtos/prod-001", json={"title": "Atualizado", "offer_ends_at": created["offer_ends_at"]})
    assert response.status_code == 200
    assert response.json()["effective_price"] == 100
    renewed = client.put("/produtos/prod-001", json={"offer_ends_at": (offer_clock.current + timedelta(days=1)).isoformat()})
    assert renewed.json()["effective_price"] == 70


def test_offer_price_constraint_is_enforced_in_database(client, db, offer_clock):
    create_offer(client, offer_clock)
    with pytest.raises(IntegrityError):
        db.execute(text("UPDATE produtos SET offer_price = price"))
    db.rollback()
    assert client.get("/produtos/prod-001").json()["offer_price"] == 70


def test_offer_changes_require_authentication(public_client):
    assert public_client.put("/produtos/prod-001", json={"offer_price": 1}).status_code == 401
