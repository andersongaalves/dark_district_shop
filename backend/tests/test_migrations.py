from io import StringIO
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect
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
            "alembic_version", "produtos", "usuarios", "produto_imagens", "produto_variantes"
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
