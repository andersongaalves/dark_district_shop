"""Administrative views and one-shot manual sends using the existing records."""
import logging
import re
from datetime import timedelta

from sqlalchemy import case, func, select, update, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

from core.config import settings
from integrations.whatsapp.client import send_text, WhatsAppDeliveryError
from models.atendimento import ChannelIdentity, Conversation, Message, utc_now
from services.customer_service import SupportError, aware
from services import conversation_service

logger = logging.getLogger(__name__)


def require_conversation(db, conversation_id, *, lock=False):
    query = select(Conversation).where(Conversation.id == conversation_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    conversation = db.scalar(query)
    if not conversation or conversation.channel != "whatsapp":
        raise SupportError("Conversa WhatsApp não encontrada.", 404)
    return conversation


def message_view(message):
    metadata = message.extra_data or {}
    status = metadata.get("delivery_status")
    if status == "sending" and aware(message.created_at) < utc_now() - timedelta(minutes=2):
        status = "uncertain"
    return {"id": message.id, "sender": message.sender, "content": message.content,
            "created_at": aware(message.created_at), "delivery_status": status}


def list_inbox(db, status=None, limit=50, offset=0):
    latest = select(Message.id).where(Message.conversation_id == Conversation.id).order_by(
        Message.created_at.desc(), Message.id.desc()).limit(1).correlate(Conversation).scalar_subquery()
    message = aliased(Message)
    query = select(Conversation, ChannelIdentity, message).join(
        ChannelIdentity, ChannelIdentity.id == Conversation.identity_id).outerjoin(message, message.id == latest
        ).where(Conversation.channel == "whatsapp")
    if status:
        query = query.where(Conversation.status == status)
    rank = case((Conversation.status == "WAITING_HUMAN", 0), (Conversation.status == "HUMAN", 1), else_=2)
    rows = db.execute(query.order_by(rank, Conversation.updated_at.desc(), Conversation.id.desc())
                      .offset(offset).limit(limit + 1)).all()
    return {"items": [{"conversation_id": c.id, "phone": identity.external_id.split(":", 1)[-1],
                       "status": c.status, "updated_at": aware(c.updated_at),
                       "last_message": message_view(m) if m else None}
                      for c, identity, m in rows[:limit]], "has_more": len(rows) > limit}


def get_messages(db, conversation_id, limit=50, before=None):
    conversation = require_conversation(db, conversation_id)
    query = select(Message).where(Message.conversation_id == conversation_id)
    if before:
        cursor = db.get(Message, before)
        if not cursor or cursor.conversation_id != conversation_id:
            raise SupportError("Página de histórico inválida.", 422)
        query = query.where(tuple_(Message.created_at, Message.id) < tuple_(cursor.created_at, cursor.id))
    rows = db.scalars(query.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit + 1)).all()
    return {"conversation_id": conversation_id, "status": conversation.status,
            "messages": [message_view(m) for m in reversed(rows[:limit])],
            "has_more": len(rows) > limit}


def set_status(db, conversation_id, status, admin_id):
    require_conversation(db, conversation_id)
    result = conversation_service.change_status(db, conversation_id, status)
    logger.info("admin_whatsapp_conversation_%s conversation_id=%s admin_id=%s",
                "claimed" if status == "HUMAN" else "closed", conversation_id, admin_id)
    return result


def send_manual(db, conversation_id, request_id, text, admin_id):
    conversation = require_conversation(db, conversation_id, lock=True)
    key = f"manual:{request_id}"
    previous = db.scalar(select(Message).where(Message.conversation_id == conversation_id,
        Message.external_id == key, Message.sender == "human"))
    if previous:
        if previous.content != text:
            raise SupportError("Identificador já utilizado por outra mensagem.", 409)
        return message_view(previous)
    if conversation.status != "HUMAN":
        raise SupportError("Assuma o atendimento antes de responder.", 409)
    identity = db.get(ChannelIdentity, conversation.identity_id)
    phone_id, recipient = identity.external_id.split(":", 1)
    if phone_id != settings.WHATSAPP_PHONE_NUMBER_ID or not re.fullmatch(r"[0-9]{5,20}", recipient):
        raise SupportError("Número de atendimento não corresponde à configuração atual.", 409)
    # Delayed/reordered webhooks must not shorten the last customer's reply window.
    timestamp = db.scalar(select(func.max(Message.extra_data["received_timestamp"].as_integer())).where(
        Message.conversation_id == conversation_id, Message.sender == "customer"))
    if timestamp is None:
        legacy_time = db.scalar(select(func.max(Message.created_at)).where(
            Message.conversation_id == conversation_id, Message.sender == "customer"))
        timestamp = aware(legacy_time).timestamp() if legacy_time else 0
    if not -300 <= utc_now().timestamp() - timestamp < 86400:
        raise SupportError("A janela de 24 horas expirou. Aguarde uma nova mensagem do cliente.", 409)
    message = Message(conversation_id=conversation_id, external_id=key, sender="human", content=text,
                      extra_data={"delivery_status": "sending", "admin_id": admin_id})
    db.add(message)
    conversation.updated_at = utc_now()
    try:
        db.flush()
        message_id = message.id
        db.commit()  # Reserve before IO; repeated requests never resend, even after a process crash.
    except IntegrityError:
        db.rollback()
        previous = db.scalar(select(Message).where(Message.conversation_id == conversation_id,
            Message.external_id == key, Message.sender == "human"))
        if not previous:
            raise
        if previous.content != text:
            raise SupportError("Identificador já utilizado por outra mensagem.", 409)
        return message_view(previous)
    metadata = {"admin_id": admin_id}
    try:
        meta_id = send_text(recipient, text)
        metadata.update(delivery_status="sent", meta_message_id=meta_id)
    except WhatsAppDeliveryError as error:
        metadata.update(delivery_status="uncertain" if error.uncertain else "failed", error_code=error.code)
    except Exception:
        metadata.update(delivery_status="uncertain", error_code="send_unknown")
    try:
        db.execute(update(Message).where(Message.id == message_id).values(extra_data=metadata))
        db.commit()
    except Exception:
        db.rollback()
        logger.error("admin_whatsapp_message_result_unrecorded conversation_id=%s", conversation_id)
        raise SupportError("Envio sem confirmação. Atualize o histórico antes de tentar novamente.", 503) from None
    logger.info("admin_whatsapp_message_%s conversation_id=%s admin_id=%s",
                metadata["delivery_status"], conversation_id, admin_id)
    return message_view(db.get(Message, message_id))
