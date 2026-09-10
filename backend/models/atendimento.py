"""Channel-neutral support records. Product and administrative domains remain separate."""
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


def utc_now():
    return datetime.now(timezone.utc)


def new_id():
    return str(uuid4())


class Channel(str, Enum):
    WEB = "web"
    WHATSAPP = "whatsapp"


class ConversationStatus(str, Enum):
    AI = "AI"
    WAITING_HUMAN = "WAITING_HUMAN"
    HUMAN = "HUMAN"


class Sender(str, Enum):
    CUSTOMER = "customer"
    ASSISTANT = "assistant"
    HUMAN = "human"
    SYSTEM = "system"


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ChannelIdentity(Base):
    __tablename__ = "channel_identities"
    __table_args__ = (
        UniqueConstraint("channel", "external_id", name="uq_identity_channel_external"),
        CheckConstraint("channel IN ('web','whatsapp')", name="ck_identity_channel"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(20))
    # Web: SHA-256 of the random credential. WhatsApp: verified account:sender ID.
    external_id: Mapped[str] = mapped_column(String(200))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint("channel IN ('web','whatsapp')", name="ck_conversation_channel"),
        CheckConstraint("status IN ('AI','WAITING_HUMAN','HUMAN')", name="ck_conversation_status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    identity_id: Mapped[str] = mapped_column(ForeignKey("channel_identities.id", ondelete="CASCADE"), unique=True)
    channel: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default=ConversationStatus.AI.value)
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=0)
    processing_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    processing_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "external_id", "sender", name="uq_message_external_sender"),
        CheckConstraint("sender IN ('customer','assistant','human','system')", name="ck_message_sender"),
        Index("ix_messages_history", "conversation_id", "created_at", "id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sender: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    extra_data: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    response_data: Mapped[dict | None] = mapped_column("response", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DeliveryJob(Base):
    __tablename__ = "delivery_jobs"
    __table_args__ = (
        CheckConstraint("kind IN ('inbound','outbound')", name="ck_delivery_kind"),
        CheckConstraint("channel = 'whatsapp'", name="ck_delivery_channel"),
        CheckConstraint("status IN ('pending','processing','sent','failed','uncertain','cancelled')", name="ck_delivery_status"),
        Index("ix_delivery_ready", "status", "available_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(20))
    external_id: Mapped[str] = mapped_column(String(200), unique=True)
    channel: Mapped[str] = mapped_column(String(20), default=Channel.WHATSAPP.value)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True, index=True)
    source_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    routing_key: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
