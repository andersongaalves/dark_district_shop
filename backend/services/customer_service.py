"""Resolve verified channel identities; never merge customers by user-provided claims."""
from datetime import timedelta, timezone
from hashlib import sha256
import re
import secrets

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.config import settings
from models.atendimento import Channel, ChannelIdentity, Conversation, Customer, utc_now
from schemas.atendimento import ChatSession


class SupportError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _create_identity(db: Session, channel, external_id, expires_at=None):
    customer = Customer()
    db.add(customer)
    db.flush()
    identity = ChannelIdentity(customer_id=customer.id, channel=channel, external_id=external_id, expires_at=expires_at)
    db.add(identity)
    db.flush()
    conversation = Conversation(customer_id=customer.id, identity_id=identity.id, channel=channel)
    db.add(conversation)
    db.flush()
    return identity, conversation


def create_web_session(db: Session) -> ChatSession:
    credential = secrets.token_urlsafe(32)
    expires_at = utc_now() + timedelta(hours=settings.CHAT_SESSION_HOURS)
    try:
        _, conversation = _create_identity(db, Channel.WEB.value, sha256(credential.encode()).hexdigest(), expires_at)
        result = ChatSession(session_id=credential, conversation_id=conversation.id, expires_at=expires_at)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def authenticate_web(db: Session, credential: str) -> Conversation:
    if not isinstance(credential, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", credential):
        raise SupportError("Sua sessão de atendimento expirou. Inicie uma nova conversa.", 401)
    identity = db.scalar(select(ChannelIdentity).where(
        ChannelIdentity.channel == Channel.WEB.value,
        ChannelIdentity.external_id == sha256(credential.encode()).hexdigest()))
    if not identity or not identity.expires_at or aware(identity.expires_at) <= utc_now():
        raise SupportError("Sua sessão de atendimento expirou. Inicie uma nova conversa.", 401)
    conversation = db.scalar(select(Conversation).where(Conversation.identity_id == identity.id))
    if not conversation:
        raise SupportError("Sua sessão de atendimento expirou. Inicie uma nova conversa.", 401)
    return conversation


def resolve_whatsapp(db: Session, external_id: str) -> Conversation:
    if not re.fullmatch(r"[0-9]{1,30}:[0-9]{5,30}", external_id):
        raise SupportError("Identidade de canal inválida.")
    def existing():
        return db.scalar(select(Conversation).join(ChannelIdentity, Conversation.identity_id == ChannelIdentity.id).where(
            ChannelIdentity.channel == Channel.WHATSAPP.value, ChannelIdentity.external_id == external_id))
    conversation = existing()
    if conversation:
        return conversation
    try:
        _, conversation = _create_identity(db, Channel.WHATSAPP.value, external_id)
        conversation_id = conversation.id
        db.commit()
        return db.get(Conversation, conversation_id)
    except IntegrityError:
        db.rollback()
        conversation = existing()
        if conversation:
            return conversation
        raise


def delete_web_session(db: Session, conversation: Conversation):
    # Remove only this identity. Future linked identities must survive a web reset.
    identity = db.get(ChannelIdentity, conversation.identity_id)
    customer_id = conversation.customer_id
    db.delete(identity)
    db.flush()
    if db.scalar(select(ChannelIdentity.id).where(ChannelIdentity.customer_id == customer_id).limit(1)) is None:
        db.delete(db.get(Customer, customer_id))
    db.commit()
