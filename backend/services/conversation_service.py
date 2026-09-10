"""One conversation pipeline for every channel, with durable message idempotency."""
from datetime import timedelta
import json
import logging
from time import perf_counter

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from core.config import settings
from models.atendimento import Channel, ChannelIdentity, Conversation, Customer, DeliveryJob, Message, Sender, new_id, utc_now
from schemas.atendimento import AgentInput, AgentResponse, ChatAction, ChatHistory, ChatReply, HistoryEntry, StoredMessage
from services.customer_service import SupportError, resolve_whatsapp

logger = logging.getLogger(__name__)


def _reply(result, conversation, message_id):
    return ChatReply(**result.model_dump(), conversation_id=conversation.id,
                     status=conversation.status, message_id=message_id)


def _silent():
    return AgentResponse(message="", type="silent")


def _find_message(db, conversation_id, message_id):
    return db.scalar(select(Message).where(Message.conversation_id == conversation_id,
        Message.external_id == message_id, Message.sender == Sender.CUSTOMER.value))


def _replay(message, conversation):
    result = AgentResponse.model_validate(message.response_data)
    if conversation.status == "HUMAN" or (conversation.status == "WAITING_HUMAN" and result.type != "handoff"):
        result = _silent()
    return _reply(result, conversation, message.external_id)


def receive(db: Session, conversation: Conversation, message_id: str, text: str) -> ChatReply:
    if not text.strip() or len(text) > settings.CHAT_MAX_MESSAGE_LENGTH or "\x00" in text:
        raise SupportError("Digite uma mensagem de até 2000 caracteres.", 422)
    if not message_id or len(message_id) > 200:
        raise SupportError("Identificador de mensagem inválido.", 422)
    text = text.strip()
    conversation_id = conversation.id
    old = _find_message(db, conversation_id, message_id)
    if old and old.content != text:
        raise SupportError("Este identificador já pertence a outra mensagem.", 409)
    if old and old.response_data is not None:
        return _replay(old, conversation)

    owner, now = new_id(), utc_now()
    acquired = db.execute(update(Conversation).where(Conversation.id == conversation_id, or_(
        Conversation.processing_until.is_(None), Conversation.processing_until <= now,
    )).values(processing_token=owner, processing_until=now + timedelta(seconds=settings.CHAT_PROCESSING_LEASE_SECONDS)),
        execution_options={"synchronize_session": False})
    db.commit()
    if acquired.rowcount != 1:
        raise SupportError("Uma mensagem ainda está em processamento. Tente novamente em instantes.", 409)
    started = perf_counter()
    try:
        db.expire_all()
        conversation = db.get(Conversation, conversation_id)
        old = _find_message(db, conversation_id, message_id)
        if old and old.response_data is not None:
            return _replay(old, conversation)
        if old is None:
            if conversation.channel == "web":
                count = db.scalar(select(func.count()).select_from(Message).where(
                    Message.conversation_id == conversation_id, Message.sender == "customer"))
                if count >= settings.CHAT_MAX_MESSAGES_PER_SESSION:
                    raise SupportError("Esta sessão atingiu o limite de mensagens. Inicie uma nova conversa.", 429)
            old = Message(conversation_id=conversation_id, external_id=message_id, sender="customer", content=text)
            db.add(old)
            db.flush()
        incoming_id = old.id
        version = conversation.version
        channel = conversation.channel
        status = conversation.status
        context = dict(conversation.context or {})
        recent = db.scalars(select(Message).where(Message.conversation_id == conversation_id,
            Message.id != incoming_id, Message.sender.in_(["customer", "assistant", "human"])
        ).order_by(Message.created_at.desc(), Message.id.desc()).limit(settings.CHAT_HISTORY_MESSAGES)).all()
        incoming = AgentInput(channel=channel, conversation_id=conversation_id, customer_id=conversation.customer_id,
            message=text, history=[HistoryEntry(sender=item.sender, content=item.content[:6000]) for item in reversed(recent)],
            context=context)
        # Persist the incoming message and release the connection before any LLM IO.
        db.commit()
        logger.info("support_received channel=%s conversation_id=%s", channel, conversation_id)
        result = _silent()
        if status == "AI":
            try:
                from services.ai_agent import respond
                result = AgentResponse.model_validate(respond(db, incoming))
            except Exception:
                db.rollback()
                logger.warning("support_agent_failed channel=%s conversation_id=%s", channel, conversation_id)
                result = AgentResponse(message="Não consegui consultar as informações agora. Tente novamente ou peça atendimento humano.",
                                       type="error", actions=[ChatAction()])
        # Any catalog reads are finished before locking the conversation for finalization.
        db.rollback()
        conversation = db.scalar(select(Conversation).where(Conversation.id == conversation_id).with_for_update())
        if not conversation:
            raise SupportError("A conversa foi encerrada.", 410)
        if conversation.processing_token != owner:
            raise SupportError("A mensagem está sendo recuperada. Tente novamente em instantes.", 409)
        if conversation.status != "AI" or conversation.version != version:
            result = _silent()
        elif result.type == "error":
            conversation.failure_count += 1
            if conversation.failure_count >= 2:
                result = AgentResponse(message="Não consegui concluir a consulta. Registrei seu pedido de atendimento humano.",
                                       type="handoff", handoff=True)
        else:
            conversation.failure_count = 0
        if result.handoff:
            conversation.status = "WAITING_HUMAN"
            conversation.version += 1
        if result.context:
            # Memory is bounded separately from the full history; never persist provider objects.
            encoded = json.dumps(result.context, ensure_ascii=False)
            if len(encoded.encode("utf-8")) <= 8000:
                conversation.context = json.loads(encoded)
        conversation.updated_at = utc_now()
        stored = db.get(Message, incoming_id)
        stored.response_data = result.model_dump(mode="json")
        if result.type != "silent" and result.message:
            db.add(Message(conversation_id=conversation_id, external_id=message_id, sender="assistant",
                           content=result.message, response_data=result.model_dump(mode="json")))
        reply = _reply(result, conversation, message_id)
        conversation.processing_token = None
        conversation.processing_until = None
        db.commit()
        logger.info("support_processed channel=%s conversation_id=%s type=%s duration_ms=%d", channel,
                    conversation_id, result.type, int((perf_counter() - started) * 1000))
        return reply
    finally:
        db.rollback()
        db.execute(update(Conversation).where(Conversation.id == conversation_id, Conversation.processing_token == owner)
            .values(processing_token=None, processing_until=None), execution_options={"synchronize_session": False})
        db.commit()


def receive_whatsapp(db: Session, external_id: str, message_id: str, text: str) -> ChatReply:
    return receive(db, resolve_whatsapp(db, external_id), message_id, text)


def history(db: Session, conversation: Conversation) -> ChatHistory:
    rows = db.scalars(select(Message).where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc(), Message.id.desc()).limit(100)).all()
    return ChatHistory(conversation_id=conversation.id, status=conversation.status, messages=[
        StoredMessage(id=row.id, external_id=row.external_id, sender=row.sender, content=row.content, created_at=row.created_at,
                      response=AgentResponse.model_validate(row.response_data) if row.response_data and row.sender != "customer" else None)
        for row in reversed(rows)])


def change_status(db: Session, conversation_id: str, status: str):
    conversation = db.scalar(select(Conversation).where(Conversation.id == conversation_id).with_for_update())
    if not conversation:
        raise SupportError("Conversa não encontrada.", 404)
    conversation.status = status
    conversation.version += 1
    conversation.updated_at = utc_now()
    if status == "AI":
        conversation.failure_count = 0
    if status != "AI":
        db.execute(update(DeliveryJob).where(DeliveryJob.conversation_id == conversation_id,
            DeliveryJob.kind == "outbound", DeliveryJob.status == "pending").values(status="cancelled", error_code="human_handoff"))
    db.add(Message(conversation_id=conversation_id, sender="system", content=f"Atendimento: {status}."))
    db.commit()
    return {"conversation_id": conversation_id, "status": status}


def list_conversations(db: Session, status: str | None = None):
    query = select(Conversation)
    if status:
        query = query.where(Conversation.status == status)
    rows = db.scalars(query.order_by(Conversation.updated_at.desc()).limit(100)).all()
    return [{"conversation_id": row.id, "channel": row.channel, "status": row.status,
             "updated_at": row.updated_at, "failure_count": row.failure_count} for row in rows]


def purge_expired(db: Session):
    """Explicit maintenance command: configured retention, no logging of customer content."""
    now = utc_now()
    cutoff = now - timedelta(days=settings.CHAT_RETENTION_DAYS)
    stale_identities = select(ChannelIdentity.id).where(ChannelIdentity.channel == "web", ChannelIdentity.expires_at < now)
    db.execute(delete(Conversation).where(or_(Conversation.updated_at < cutoff, Conversation.identity_id.in_(stale_identities))))
    db.execute(delete(ChannelIdentity).where(~ChannelIdentity.id.in_(select(Conversation.identity_id))))
    db.execute(delete(Customer).where(~Customer.id.in_(select(ChannelIdentity.customer_id))))
    db.execute(delete(DeliveryJob).where(DeliveryJob.created_at < cutoff, DeliveryJob.status != "processing"))
    db.commit()
