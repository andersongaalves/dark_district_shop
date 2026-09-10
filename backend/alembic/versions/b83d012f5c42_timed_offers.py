"""Add promotional price and optional offer deadline without changing base prices."""
from alembic import op
import sqlalchemy as sa

revision = "b83d012f5c42"
down_revision = "a72c901e4b31"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("produtos", sa.Column("offer_price", sa.Float(), nullable=True))
    op.add_column("produtos", sa.Column("offer_ends_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("produtos") as batch:
        batch.create_check_constraint("ck_produtos_offer_price", "offer_price IS NULL OR (offer_price >= 0 AND offer_price < price)")


def downgrade():
    with op.batch_alter_table("produtos") as batch:
        batch.drop_constraint("ck_produtos_offer_price", type_="check")
        batch.drop_column("offer_ends_at")
        batch.drop_column("offer_price")
