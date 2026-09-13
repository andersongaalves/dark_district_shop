"""Bounded reuse of the site's factual agent, without any commercial write tools."""
import hashlib
import logging
import re
from datetime import timedelta
from sqlalchemy import select, update, or_
from core.config import settings
from models.atendimento import Conversation, Message, HandoffReason, utc_now, new_id
from schemas.atendimento import AgentInput, HistoryEntry
from services import ai_agent
from services.agent_language import normalize
from services.customer_service import SupportError

logger = logging.getLogger(__name__)
PURCHASE_TEXT = "Perfeito 🖤 Vou encaminhar você para um atendente da Dark District para finalizar sua compra. Em breve ele continua por aqui."
HANDOFF_TEXT = "Vou encaminhar sua solicitação para um atendente da Dark District. O atendimento automático fica pausado enquanto você aguarda."


def change_mode(db, conversation_id, mode):
    from services.whatsapp_inbox_service import require_conversation
    from services.whatsapp_hybrid_service import handoff
    c = require_conversation(db, conversation_id, lock=True)
    if mode != "OFF" and not settings.AI_WHATSAPP_ENABLED:
        raise SupportError("Ative AI_WHATSAPP_ENABLED no servidor primeiro.", 409)
    c.ai_mode = mode
    c.version += 1
    c.context = {k: v for k, v in (c.context or {}).items() if k != "suggestion_cache"}
    if c.status == "AI" and mode != "AUTO":
        source = db.scalar(select(Message).where(Message.conversation_id == c.id, Message.sender == "customer")
                           .order_by(Message.created_at.desc()).limit(1))
        if source:
            handoff(db, c, "HUMAN_REQUESTED", source, transition=False)
        else:
            c.status = "WAITING_HUMAN"
    c.updated_at = utc_now()
    db.commit()
    logger.info("conversation_ai_mode_changed conversation_id=%s mode=%s", conversation_id, mode)
    return {"ai_mode": c.ai_mode, "status": c.status}


def reason_for(text):
    text = normalize(text)
    patterns = [
        ("HUMAN_REQUESTED", r"humano|atendente|pessoa real|falar com (?:uma )?pessoa|tem alguem|pessoa de verdade"),
        ("PAYMENT", r"\bpix\b|pagamento|pagar|chave|cobranca|cartao|boleto"),
        ("PURCHASE_INTENT", r"quero comprar|vou levar|quero (?:essa|esse|esta|este)|separa|reserv|quero fechar|quero (?:duas|dois|uma|um|\d+) (?:dessa|desse)|fazer meu pedido|fecha.*compra"),
        ("RETURN_EXCHANGE", r"troca|devolu|devolver|reembolso|estorno"),
        ("COMPLAINT", r"reclam|fraude|golpe|defeito|problema sensivel"),
        ("DELIVERY_ISSUE", r"nao chegou|atras|problema.*entrega|entrega.*problema"),
        ("ORDER_SUPPORT", r"\bpedido\b|cancel"),
        ("NEGOTIATION", r"desconto|negoci|mais barato|faz por"),
    ]
    return next((HandoffReason(reason).value for reason, pattern in patterns if re.search(pattern, text)), None)


def agent_input(db, conversation, source=None):
    rows = db.scalars(select(Message).where(Message.conversation_id == conversation.id,
        Message.sender.in_(["customer", "assistant", "human"]),
        or_(Message.sender == "customer", Message.extra_data["delivery_status"].as_string() == "sent",
            Message.extra_data["delivery_status"].as_string().is_(None)),
        or_(Message.extra_data["cycle"].as_integer() == conversation.cycle,
            (Message.extra_data["cycle"].as_integer().is_(None)) if conversation.cycle == 1 else False)
    ).order_by(Message.created_at.desc(), Message.id.desc()).limit(settings.CHAT_HISTORY_MESSAGES)).all()
    source = source or next((m for m in rows if m.sender == "customer"), None)
    if not source:
        raise SupportError("Não há mensagem do cliente neste ciclo.", 409)
    context = {key: value for key, value in (conversation.context or {}).items() if key != "suggestion_cache"}
    context.update(status=conversation.status, ai_mode=conversation.ai_mode, handoff_reason=conversation.handoff_reason)
    return AgentInput(channel="whatsapp", conversation_id=conversation.id, customer_id=conversation.customer_id,
        message=source.content[:2000], history=[HistoryEntry(sender=m.sender, content=m.content[:1000])
        for m in reversed(rows) if m.id != source.id], context=context)


def suggest(db, conversation_id, force=False):
    from services.whatsapp_inbox_service import require_conversation
    c = require_conversation(db, conversation_id)
    if not settings.AI_WHATSAPP_ENABLED or c.ai_mode == "OFF" or c.status == "CLOSED":
        raise SupportError("Assistente desativado nesta conversa.", 409)
    incoming = agent_input(db, c)
    fingerprint = hashlib.sha256(incoming.model_dump_json().encode()).hexdigest()
    cached = (c.context or {}).get("suggestion_cache", {})
    if not force and cached.get("fingerprint") == fingerprint and cached.get("expires", 0) > utc_now().timestamp():
        return {"message": cached["message"], "cached": True}
    owner, version = new_id(), c.version
    acquired = db.execute(update(Conversation).where(Conversation.id == c.id, or_(
        Conversation.processing_until.is_(None), Conversation.processing_until < utc_now())).values(
        processing_token=owner, processing_until=utc_now() + timedelta(seconds=settings.CHAT_PROCESSING_LEASE_SECONDS)))
    db.commit()
    if not acquired.rowcount:
        raise SupportError("Sugestão em processamento. Aguarde.", 409)
    try:
        result = ai_agent.respond(db, incoming)
        db.rollback()
        c = require_conversation(db, conversation_id, lock=True)
        if c.version != version or c.processing_token != owner:
            raise SupportError("A conversa mudou. Gere uma nova sugestão.", 409)
        if result.type == "error":
            raise SupportError("Não foi possível consultar dados confiáveis.", 503)
        # All factual prose is produced by the same read-only tools, never raw LLM text.
        text = result.message[:2000]
        c.context = {**(c.context or {}), **result.context}
        fingerprint = hashlib.sha256(agent_input(db, c).model_dump_json().encode()).hexdigest()
        c.context = {**c.context, "suggestion_cache": {"fingerprint": fingerprint,
            "expires": utc_now().timestamp() + 30, "message": text}}
        db.commit()
        logger.info("ai_suggestion_generated conversation_id=%s", conversation_id)
        return {"message": text, "cached": False}
    finally:
        db.rollback()
        db.execute(update(Conversation).where(Conversation.id == conversation_id, Conversation.processing_token == owner)
                   .values(processing_token=None, processing_until=None))
        db.commit()
