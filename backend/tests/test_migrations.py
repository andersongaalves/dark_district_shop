from io import StringIO
from pathlib import Path
import logging.config

import pytest

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from pydantic import SecretStr

from core.config import settings
from database import Base


@pytest.fixture(autouse=True)
def preserve_test_logging(monkeypatch):
    # Alembic's fileConfig otherwise disables application loggers globally and
    # removes pytest's capture handlers from unrelated tests in this process.
    monkeypatch.setattr(logging.config, "fileConfig", lambda *args, **kwargs: None)


def test_migrations_match_models_on_fresh_database(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'migration.sqlite').as_posix()}"
    monkeypatch.setattr(settings, "DATABASE_URL", SecretStr(database_url))
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(database_url)
    try:
        assert set(inspect(engine).get_table_names()) == {
            "alembic_version", "produtos", "usuarios", "produto_imagens", "produto_variantes", "categorias", "colecoes",
            "customers", "channel_identities", "conversations", "messages", "delivery_jobs",
        }
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            assert compare_metadata(context, Base.metadata) == []
    finally:
        engine.dispose()


def test_postgresql_migration_compiles_offline(monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_URL", SecretStr("postgresql://localhost/offline_test"))
    output = StringIO()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"), output_buffer=output)
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    for table in ["produtos", "usuarios", "produto_imagens", "produto_variantes"]:
        assert f"CREATE TABLE {table}" in sql
    assert "ALTER TABLE produtos ALTER COLUMN category_id SET NOT NULL" in sql
    assert "setval" in sql
    assert "CHECK (status IN ('AI','WAITING_HUMAN','HUMAN','CLOSED'))" in sql


def test_inbox_migration_preserves_conversation_history(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'inbox.sqlite').as_posix()}"
    monkeypatch.setattr(settings, "DATABASE_URL", SecretStr(url))
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "c94e123a6d53")
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO customers VALUES ('customer', CURRENT_TIMESTAMP)"))
            connection.execute(text("INSERT INTO channel_identities VALUES ('identity', 'customer', 'whatsapp', '123:5511999999999', NULL, CURRENT_TIMESTAMP)"))
            connection.execute(text("""INSERT INTO conversations
                (id,customer_id,identity_id,channel,status,context,failure_count,version,created_at,updated_at)
                VALUES ('conversation','customer','identity','whatsapp','HUMAN','{}',0,0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"""))
            connection.execute(text("""INSERT INTO messages (id,conversation_id,external_id,sender,content,metadata,created_at)
                VALUES ('message','conversation','wamid.original','customer','Olá','{}',CURRENT_TIMESTAMP)"""))
        command.upgrade(config, "head")
        with engine.begin() as connection:
            connection.execute(text("UPDATE conversations SET status='CLOSED'"))
            assert connection.scalar(text("SELECT content FROM messages")) == "Olá"
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
        command.downgrade(config, "c94e123a6d53")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT status FROM conversations")) == "HUMAN"
            assert connection.scalar(text("SELECT content FROM messages")) == "Olá"
    finally:
        engine.dispose()


def test_upgrade_and_downgrade_preserve_populated_database(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'legacy.sqlite').as_posix()}"
    monkeypatch.setattr(settings, "DATABASE_URL", SecretStr(url))
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "fc910ce70e6d")
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            for index, category in enumerate(["Camisetas", "Camisetas", "Calças", "", " camisetas "]):
                connection.execute(text("""
                    INSERT INTO produtos VALUES (:id, 'Peça', 'Descrição', 79.9,
                    :category, 'Unissex', TRUE, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """), {"id": f"piece-{index}", "category": category})
            connection.execute(text("INSERT INTO produto_imagens VALUES (7, 'piece-0', 'https://example.com/a.jpg', 0)"))
            connection.execute(text("INSERT INTO produto_variantes VALUES (8, 'piece-0', 'G', 'Preto', 1)"))
        command.upgrade(config, "head")
        with engine.connect() as connection:
            rows = connection.execute(text("SELECT * FROM produtos ORDER BY id")).mappings().all()
            assert len(rows) == 5
            assert all(row["product_type"] == "catalogo" and not row["is_offer"] for row in rows)
            assert all(row["category_id"] and row["collection_id"] is None for row in rows)
            assert rows[0]["category_id"] == rows[1]["category_id"]
            assert connection.scalar(text("SELECT COUNT(*) FROM categorias")) == 4
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
            assert connection.scalar(text("SELECT id FROM produto_variantes")) == 8
            assert connection.scalar(text("SELECT id FROM produto_imagens")) == 7
        command.downgrade(config, "fc910ce70e6d")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT COUNT(*) FROM produtos")) == 5
            assert connection.scalar(text("SELECT id FROM produto_variantes")) == 8
            assert connection.scalar(text("SELECT id FROM produto_imagens")) == 7
            assert connection.execute(text("SELECT category FROM produtos ORDER BY id")).scalars().all() == ["Camisetas", "Camisetas", "Calças", "", " camisetas "]
    finally:
        engine.dispose()


def test_timed_offer_migration_preserves_prices_and_existing_offer_flags(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'offers.sqlite').as_posix()}"
    monkeypatch.setattr(settings, "DATABASE_URL", SecretStr(url))
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "a72c901e4b31")
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO categorias VALUES (1, 'Camisetas', 'camisetas', TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
            connection.execute(text("""INSERT INTO produtos (id,title,description,price,category,gender,available,featured,created_at,updated_at,category_id,is_offer)
                VALUES ('legacy','Peça','Descrição',99.9,'Camisetas','',TRUE,FALSE,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,1,TRUE)"""))
        command.upgrade(config, "head")
        with engine.connect() as connection:
            row = connection.execute(text("SELECT price,is_offer,offer_price,offer_ends_at FROM produtos")).one()
            assert tuple(row) == (99.9, 1, None, None)
        command.downgrade(config, "a72c901e4b31")
        with engine.connect() as connection:
            assert tuple(connection.execute(text("SELECT price,is_offer FROM produtos")).one()) == (99.9, 1)
    finally:
        engine.dispose()
