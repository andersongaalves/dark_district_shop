from io import StringIO
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from pydantic import SecretStr

from core.config import settings
from database import Base


def test_migrations_match_models_on_fresh_database(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'migration.sqlite').as_posix()}"
    monkeypatch.setattr(settings, "DATABASE_URL", SecretStr(database_url))
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(database_url)
    try:
        assert set(inspect(engine).get_table_names()) == {
            "alembic_version", "produtos", "usuarios", "produto_imagens", "produto_variantes", "categorias", "colecoes"
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
