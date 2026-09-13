"""Separate AI permission, operational status and service cycle."""
from alembic import op
import sqlalchemy as sa

revision = "e16a345c8f75"
down_revision = "d05f234b7e64"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("conversations") as batch:
        batch.add_column(sa.Column("ai_mode", sa.String(10), nullable=False, server_default="OFF"))
        batch.add_column(sa.Column("cycle", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("handoff_reason", sa.String(30), nullable=True))
        batch.create_check_constraint("ck_conversation_ai_mode", "ai_mode IN ('AUTO','ASSIST','OFF')")
        batch.create_check_constraint("ck_conversation_cycle", "cycle >= 1")
        batch.create_check_constraint("ck_conversation_handoff", "handoff_reason IS NULL OR handoff_reason IN ('HUMAN_REQUESTED','PURCHASE_INTENT','PAYMENT','ORDER_SUPPORT','COMPLAINT','RETURN_EXCHANGE','NEGOTIATION','LOW_CONFIDENCE','AI_FAILURE','DELIVERY_ISSUE')")


def downgrade():
    with op.batch_alter_table("conversations") as batch:
        batch.drop_constraint("ck_conversation_handoff", type_="check")
        batch.drop_constraint("ck_conversation_cycle", type_="check")
        batch.drop_constraint("ck_conversation_ai_mode", type_="check")
        batch.drop_column("handoff_reason")
        batch.drop_column("cycle")
        batch.drop_column("ai_mode")
