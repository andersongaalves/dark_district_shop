"""Bounded reuse of the site's factual agent, without any commercial write tools."""
import hashlib
import logging
import re
from datetime import timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select, update, or_
from core.config import settings
from models.atendimento import Conversation, Message, HandoffReason, utc_now, new_id
from schemas.atendimento import AgentInput, AgentResponse, HistoryEntry
from services import ai_agent
from services.agent_language import normalize
from services.customer_service import SupportError

logger = logging.getLogger(__name__)
PURCHASE_TEXT = "Perfeito 🖤 Vou encaminhar você para um atendente da Dark District para finalizar sua compra. Em breve ele continua por aqui."
HANDOFF_TEXT = "Vou encaminhar sua solicitação para um atendente da Dark District. O atendimento automático fica pausado enquanto você aguarda."


class DecisionAction(str, Enum):
    ANSWER = "ANSWER"
    CLARIFY = "CLARIFY"
    HANDOFF = "HANDOFF"
    NO_ACTION = "NO_ACTION"


class WhatsAppDecision(BaseModel):
    """Validated channel policy; AgentResponse remains presentation content."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    action: DecisionAction
    response: AgentResponse | None = None
    handoff_reason: HandoffReason | None = None
    reason_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Z][A-Z0-9_]*$")
    context_patch: dict[str, Any] = Field(default_factory=dict)
    failure_kind: str | None = Field(default=None, min_length=1, max_length=80, pattern=r"^[A-Z][A-Z0-9_]*$")
    retryable: bool = False

    @model_validator(mode="after")
    def validate_action_contract(self):
        if self.action in {DecisionAction.ANSWER, DecisionAction.CLARIFY} and self.response is None:
            raise ValueError("ANSWER e CLARIFY exigem response.")
        if self.action == DecisionAction.HANDOFF and self.handoff_reason is None:
            raise ValueError("HANDOFF exige handoff_reason.")
        if self.action == DecisionAction.NO_ACTION and (self.response is not None or self.handoff_reason is not None):
            raise ValueError("NO_ACTION não pode produzir resposta ou handoff.")
        return self


def no_action(reason_code):
    return WhatsAppDecision(action=DecisionAction.NO_ACTION, reason_code=reason_code)


def auto_state_decision(conversation):
    """Return NO_ACTION when the persisted mode/status blocks automatic replies."""
    if conversation.ai_mode != "AUTO":
        return no_action(f"AI_MODE_{conversation.ai_mode}" if conversation.ai_mode in {"ASSIST", "OFF"} else "AI_MODE_INVALID")
    if conversation.status != "AI":
        return no_action(f"STATUS_{conversation.status}" if conversation.status in {"WAITING_HUMAN", "HUMAN", "CLOSED"} else "STATUS_INVALID")
    return None


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


def _hard_handoff_reason(text):
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
    return next((HandoffReason(reason) for reason, pattern in patterns if re.search(pattern, text)), None)


def hard_handoff_decision(text):
    """Apply critical deterministic rules before any LLM or catalog planning."""
    reason = _hard_handoff_reason(text)
    if reason is None:
        return None
    return WhatsAppDecision(
        action=DecisionAction.HANDOFF,
        handoff_reason=reason,
        reason_code=reason.value,
    )


def reason_for(text):
    """Compatibility helper for callers that still need only the handoff reason."""
    decision = hard_handoff_decision(text)
    return decision.handoff_reason.value if decision else None


def _agent_context_patch(response):
    allowed = {"filters", "product_ids", "pending_correction"}
    return {key: value for key, value in response.context.items() if key in allowed}


def decision_from_agent_response(raw_response):
    """Map validated agent output to channel policy without inspecting prose."""
    try:
        response = AgentResponse.model_validate(raw_response)
    except (ValidationError, TypeError, ValueError):
        return WhatsAppDecision(
            action=DecisionAction.HANDOFF,
            handoff_reason=HandoffReason.AI_FAILURE,
            reason_code="INVALID_AGENT_RESPONSE",
            failure_kind="INVALID_AGENT_RESPONSE",
        )
    context_patch = _agent_context_patch(response)
    if response.type == "error":
        return WhatsAppDecision(
            action=DecisionAction.HANDOFF,
            handoff_reason=HandoffReason.AI_FAILURE,
            reason_code="AGENT_ERROR",
            context_patch=context_patch,
            failure_kind="AGENT_ERROR",
        )
    if response.type == "handoff" or response.handoff:
        return WhatsAppDecision(
            action=DecisionAction.HANDOFF,
            handoff_reason=HandoffReason.HUMAN_REQUESTED,
            reason_code="AGENT_HUMAN_REQUESTED",
            context_patch=context_patch,
        )
    if response.type == "silent":
        return no_action("AGENT_SILENT")
    if response.decision_hint == "CLARIFY":
        return WhatsAppDecision(
            action=DecisionAction.CLARIFY,
            response=response,
            reason_code=response.decision_reason_code or "AMBIGUOUS_MESSAGE",
            context_patch=context_patch,
        )
    return WhatsAppDecision(
        action=DecisionAction.ANSWER,
        response=response,
        reason_code="SUPPORTED_RESPONSE",
        context_patch=context_patch,
    )


def decide(db, incoming):
    """Resolve one WhatsApp turn into a validated operational decision."""
    hard_handoff = hard_handoff_decision(incoming.message)
    if hard_handoff:
        return hard_handoff
    try:
        return decision_from_agent_response(ai_agent.respond(db, incoming))
    except Exception:
        logger.warning("whatsapp_ai_decision_failed conversation_id=%s", incoming.conversation_id)
        return WhatsAppDecision(
            action=DecisionAction.HANDOFF,
            handoff_reason=HandoffReason.AI_FAILURE,
            reason_code="AGENT_EXCEPTION",
            failure_kind="AGENT_EXCEPTION",
        )


def context_after_decision(current, decision, source_message_id):
    """Persist the minimal versioned V2 state while keeping legacy context compatible."""
    context = {key: value for key, value in (current if isinstance(current, dict) else {}).items()
               if key != "suggestion_cache"}
    context.update(_agent_context_patch(decision.response) if decision.response else {})
    context.update({key: value for key, value in decision.context_patch.items()
                    if key in {"filters", "product_ids", "pending_correction"}})
    existing_v2 = context.get("conversation_v2")
    v2 = dict(existing_v2) if isinstance(existing_v2, dict) else {}
    v2["schema_version"] = 1
    v2["last_decision"] = {
        "action": decision.action.value,
        "reason_code": decision.reason_code,
        "source_message_id": str(source_message_id)[:80],
    }
    context["conversation_v2"] = v2
    return context


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
