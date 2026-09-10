"""Relational categories, collections and independent product flags.

Revision ID: a72c901e4b31
Revises: fc910ce70e6d
"""
from alembic import op
import sqlalchemy as sa

revision = "a72c901e4b31"
down_revision = "fc910ce70e6d"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("categorias", "colecoes"):
        columns = [
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(100), nullable=False, unique=True),
            sa.Column("slug", sa.String(120), nullable=False, unique=True),
            sa.Column("active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        ]
        if table == "colecoes":
            columns.append(sa.Column("description", sa.Text(), nullable=True))
        op.create_table(table, *columns)

    op.add_column("produtos", sa.Column("product_type", sa.String(20), server_default="catalogo", nullable=False))
    op.add_column("produtos", sa.Column("is_offer", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("produtos", sa.Column("category_id", sa.Integer(), nullable=True))
    op.add_column("produtos", sa.Column("collection_id", sa.Integer(), nullable=True))

    # Preserve exact legacy names, including accents/case/whitespace. Numeric slugs
    # avoid collisions during backfill and can be edited later through the ADM.
    op.execute("""
        INSERT INTO categorias (id, name, slug, active, created_at, updated_at)
        SELECT category_number, category, 'legacy-' || CAST(category_number AS VARCHAR),
               TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM (
            SELECT category, ROW_NUMBER() OVER (ORDER BY category) AS category_number
            FROM (SELECT DISTINCT category FROM produtos) AS legacy_names
        ) AS legacy_categories
    """)
    op.execute("UPDATE produtos SET category_id = (SELECT id FROM categorias WHERE categorias.name = produtos.category)")
    if op.get_context().dialect.name == "postgresql":
        op.execute("SELECT setval(pg_get_serial_sequence('categorias', 'id'), COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM categorias")

    # PostgreSQL uses native ALTER TABLE. Batch mode supports isolated SQLite tests.
    with op.batch_alter_table("produtos") as batch:
        batch.alter_column("category_id", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key("fk_produtos_category", "categorias", ["category_id"], ["id"], ondelete="RESTRICT")
        batch.create_foreign_key("fk_produtos_collection", "colecoes", ["collection_id"], ["id"], ondelete="RESTRICT")
        batch.create_check_constraint("ck_produtos_product_type", "product_type IN ('catalogo', 'brecho', 'drop')")
        batch.create_index("ix_produtos_category_id", ["category_id"])
        batch.create_index("ix_produtos_collection_id", ["collection_id"])


def downgrade():
    # Keep the latest category names for the previous application's text contract.
    op.execute("UPDATE produtos SET category = (SELECT name FROM categorias WHERE categorias.id = produtos.category_id)")
    with op.batch_alter_table("produtos") as batch:
        batch.drop_index("ix_produtos_category_id")
        batch.drop_index("ix_produtos_collection_id")
        batch.drop_constraint("fk_produtos_category", type_="foreignkey")
        batch.drop_constraint("fk_produtos_collection", type_="foreignkey")
        batch.drop_constraint("ck_produtos_product_type", type_="check")
        for column in ("category_id", "collection_id", "product_type", "is_offer"):
            batch.drop_column(column)
    op.drop_table("colecoes")
    op.drop_table("categorias")
