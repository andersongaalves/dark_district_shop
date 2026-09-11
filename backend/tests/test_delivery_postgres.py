"""Opt-in concurrency checks against a dedicated PostgreSQL test database.

Set TEST_POSTGRES_URL explicitly. Never falls back to the application's database.
Every test creates and drops only its own randomly named schema.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from channels.whatsapp_channel import IncomingText
from database import Base
from models.atendimento import DeliveryJob
from services import delivery_service as delivery


@pytest.fixture
def pg_sessions():
    url = os.environ.get("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TEST_POSTGRES_URL not set; PostgreSQL concurrency requires a dedicated test database")
    if make_url(url).get_backend_name() != "postgresql":
        pytest.fail("TEST_POSTGRES_URL must point to a dedicated PostgreSQL test database")
    engine = create_engine(url, hide_parameters=True, pool_pre_ping=True, connect_args={"connect_timeout": 10})
    schema = "dd_worker_test_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(CreateSchema(schema))
    isolated = engine.execution_options(schema_translate_map={None: schema})
    try:
        Base.metadata.create_all(isolated)
        yield sessionmaker(bind=isolated, autoflush=False)
    finally:
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        engine.dispose()


def message(identifier, sender="5511999990000"):
    return IncomingText("1234567", sender, identifier, "Olá", int(datetime.now(timezone.utc).timestamp()))


def test_two_postgres_workers_cannot_claim_the_same_job(pg_sessions):
    with pg_sessions() as db:
        delivery.enqueue_inbound(db, [message("wamid.only")])
    barrier = Barrier(2)
    def claim(_):
        barrier.wait(timeout=10)
        return delivery.claim_next(pg_sessions)
    with ThreadPoolExecutor(max_workers=2) as executor:
        claimed = list(executor.map(claim, range(2)))
    assert len([job for job in claimed if job is not None]) == 1


def test_concurrent_postgres_webhooks_preserve_one_event(pg_sessions):
    barrier = Barrier(2)
    def enqueue(_):
        barrier.wait(timeout=10)
        with pg_sessions() as db:
            return delivery.enqueue_inbound(db, [message("wamid.duplicate")])
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sum(executor.map(enqueue, range(2))) == 1
    with pg_sessions() as db:
        assert len(db.scalars(select(DeliveryJob)).all()) == 1


def test_postgres_workers_keep_identity_order_and_allow_other_customers(pg_sessions):
    with pg_sessions() as db:
        delivery.enqueue_inbound(db, [message("wamid.first"), message("wamid.second"),
                                      message("wamid.other", sender="5511888880000")])
    first = delivery.claim_next(pg_sessions)
    other = delivery.claim_next(pg_sessions)
    assert first.payload["message_id"] == "wamid.first"
    assert other.payload["message_id"] == "wamid.other"
    assert delivery.claim_next(pg_sessions) is None
    delivery._finish(first, "sent", session_factory=pg_sessions)
    assert delivery.claim_next(pg_sessions).payload["message_id"] == "wamid.second"
