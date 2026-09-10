"""Persist multichannel identities, conversations, messages and delivery jobs."""
from alembic import op
import sqlalchemy as sa

revision = "c94e123a6d53"
down_revision = "b83d012f5c42"
branch_labels = None
depends_on = None


def key():
    return sa.Column("id", sa.String(36), primary_key=True)


def timestamp(name, nullable=False):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade():
    op.create_table("customers", key(), timestamp("created_at"))
    op.create_table("channel_identities", key(),
        sa.Column("customer_id", sa.String(36), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=False),
        timestamp("expires_at", True), timestamp("created_at"),
        sa.UniqueConstraint("channel", "external_id", name="uq_identity_channel_external"),
        sa.CheckConstraint("channel IN ('web','whatsapp')", name="ck_identity_channel"))
    op.create_index("ix_channel_identities_customer_id", "channel_identities", ["customer_id"])
    op.create_table("conversations", key(),
        sa.Column("customer_id", sa.String(36), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("identity_id", sa.String(36), sa.ForeignKey("channel_identities.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("processing_token", sa.String(36), nullable=True),
        timestamp("processing_until", True), timestamp("created_at"), timestamp("updated_at"),
        sa.CheckConstraint("channel IN ('web','whatsapp')", name="ck_conversation_channel"),
        sa.CheckConstraint("status IN ('AI','WAITING_HUMAN','HUMAN')", name="ck_conversation_status"))
    op.create_index("ix_conversations_customer_id", "conversations", ["customer_id"])
    op.create_index("ix_conversations_updated_at", "conversations", ["updated_at"])
    op.create_table("messages", key(),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=True),
        sa.Column("sender", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("response", sa.JSON(), nullable=True), timestamp("created_at"),
        sa.UniqueConstraint("conversation_id", "external_id", "sender", name="uq_message_external_sender"),
        sa.CheckConstraint("sender IN ('customer','assistant','human','system')", name="ck_message_sender"))
    op.create_index("ix_messages_history", "messages", ["conversation_id", "created_at", "id"])
    op.create_table("delivery_jobs", key(),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=False, unique=True),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("source_message_id", sa.String(200), nullable=True),
        sa.Column("routing_key", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        timestamp("available_at"), timestamp("locked_at", True), timestamp("created_at"), timestamp("updated_at"),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.CheckConstraint("kind IN ('inbound','outbound')", name="ck_delivery_kind"),
        sa.CheckConstraint("channel = 'whatsapp'", name="ck_delivery_channel"),
        sa.CheckConstraint("status IN ('pending','processing','sent','failed','uncertain','cancelled')", name="ck_delivery_status"))
    op.create_index("ix_delivery_ready", "delivery_jobs", ["status", "available_at"])
    op.create_index("ix_delivery_jobs_conversation_id", "delivery_jobs", ["conversation_id"])
    op.create_index("ix_delivery_jobs_routing_key", "delivery_jobs", ["routing_key"])


def downgrade():
    for table in ("delivery_jobs", "messages", "conversations", "channel_identities", "customers"):
        op.drop_table(table)
