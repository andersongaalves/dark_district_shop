"""Bounded reuse of the site's factual agent, without any commercial write tools."""
import hashlib
import logging
import re
from datetime import timedelta
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy import select, update, or_
from core.config import settings
from models.atendimento import Conversation, Message, HandoffReason, utc_now, new_id
from schemas.atendimento import AgentInput, AgentResponse, HistoryEntry
from schemas.produto import Garment, ProductType
from services import ai_agent
from services.agent_language import COLORS, PIECES, normalize, wants_products
from services.customer_service import SupportError

logger = logging.getLogger(__name__)
PURCHASE_TEXT = "Perfeito 🖤 Vou encaminhar você para um atendente da Dark District para finalizar sua compra. Em breve ele continua por aqui."
HANDOFF_TEXT = "Vou encaminhar sua solicitação para um atendente da Dark District. O atendimento automático fica pausado enquanto você aguarda."
AUTO_WELCOME_TEXT = (
    "🖤 Olá! O atendimento automático da Dark District está ativo.\n\n"
    "Posso ajudar com produtos, preços, tamanhos, disponibilidade e outras dúvidas.\n\n"
    "Se quiser falar com um atendente humano, é só pedir."
)
AI_RESUMED_TEXT = (
    "🖤 O atendimento automático foi retomado.\n\n"
    "Se precisar falar com um atendente humano novamente, é só pedir."
)
MAX_CLARIFICATION_ATTEMPTS = 2
WHATSAPP_CONTEXT_HISTORY_LIMIT = 12
MAX_FOCUS_PRODUCTS = 10

STYLE_TERMS = {
    "dark": "dark",
    "oversized": "oversized",
    "gotico": "gotico",
    "gotica": "gotico",
    "gothic": "gotico",
    "streetwear": "streetwear",
    "punk": "punk",
    "minimalista": "minimalista",
    "estampa grande": "estampa grande",
    "discreto": "discreto",
    "discreta": "discreto",
}

PROCESS_TOPIC_OPTIONS = ["compra", "entrega", "troca_devolucao", "atendimento", "catalogo"]
PROCESS_TOPIC_PROMPTS = {
    1: "Claro 🖤 Qual processo você quer conhecer melhor? Posso explicar compra, entrega, "
       "troca/devolução, atendimento ou como funciona o catálogo da Dark District.",
    2: "Sem problema 🖤 Você quer saber o que acontece antes de comprar, como recebe o pedido, "
       "como funciona troca/devolução, o atendimento ou o catálogo?",
}
GENERAL_CLARIFICATION_PROMPT = (
    "Sem problema 🖤 Você procura uma peça ou quer saber sobre compra, entrega, "
    "troca/devolução, atendimento ou catálogo?"
)
ClarificationOption = Literal["compra", "entrega", "troca_devolucao", "atendimento", "catalogo"]


class DecisionAction(str, Enum):
    ANSWER = "ANSWER"
    CLARIFY = "CLARIFY"
    HANDOFF = "HANDOFF"
    NO_ACTION = "NO_ACTION"


class ClarificationState(BaseModel):
    """Small persisted state for the active clarification cycle."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    attempts: int = Field(ge=1, le=MAX_CLARIFICATION_ATTEMPTS)
    kind: Literal["PROCESS_TOPIC", "GENERAL"]
    options: list[ClarificationOption] = Field(default_factory=list, max_length=5)
    source_message_id: str | None = Field(default=None, min_length=1, max_length=80)


class ProductFocus(BaseModel):
    """Bounded product references for the current conversation cycle."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    product_ids: list[str] = Field(default_factory=list, max_length=MAX_FOCUS_PRODUCTS)
    selected_product_id: str | None = Field(default=None, min_length=1, max_length=50)

    @field_validator("product_ids", mode="before")
    @classmethod
    def unique_bounded_ids(cls, values):
        result = []
        for value in values if isinstance(values, list) else []:
            if isinstance(value, str) and 0 < len(value) <= 50 and value not in result:
                result.append(value)
            if len(result) == MAX_FOCUS_PRODUCTS:
                break
        return result

    @model_validator(mode="after")
    def selected_must_be_presented(self):
        if self.selected_product_id and self.selected_product_id not in self.product_ids:
            self.selected_product_id = None
        return self


class ConversationPreferences(BaseModel):
    """Allowlisted discovery preferences; never a permanent customer profile."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    garment: Garment | None = None
    style_query: str | None = Field(default=None, min_length=1, max_length=100)
    size: str | None = Field(default=None, min_length=1, max_length=50)
    color: str | None = Field(default=None, min_length=1, max_length=100)
    max_price: float | None = Field(default=None, ge=0, le=1_000_000, allow_inf_nan=False)
    product_type: ProductType | None = None
    offer_only: bool | None = None

    @field_validator("style_query")
    @classmethod
    def allow_style(cls, value):
        normalized = normalize(value) if value else value
        if normalized not in set(STYLE_TERMS.values()):
            raise ValueError("Estilo fora da allowlist.")
        return normalized

    @field_validator("size")
    @classmethod
    def allow_size(cls, value):
        normalized = value.strip().upper() if value else value
        if not re.fullmatch(r"PP|P|M|G|GG|XG|XXG|3[4-9]|[45][0-9]|60", normalized):
            raise ValueError("Tamanho inválido.")
        return normalized

    @field_validator("color")
    @classmethod
    def allow_color(cls, value):
        normalized = normalize(value) if value else value
        if normalized not in set(COLORS.values()):
            raise ValueError("Cor fora da allowlist.")
        return normalized


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
    clarification: ClarificationState | None = None
    clear_clarification: bool = False

    @model_validator(mode="after")
    def validate_action_contract(self):
        if self.action in {DecisionAction.ANSWER, DecisionAction.CLARIFY} and self.response is None:
            raise ValueError("ANSWER e CLARIFY exigem response.")
        if self.action == DecisionAction.HANDOFF and self.handoff_reason is None:
            raise ValueError("HANDOFF exige handoff_reason.")
        if self.action == DecisionAction.NO_ACTION and (self.response is not None or self.handoff_reason is not None):
            raise ValueError("NO_ACTION não pode produzir resposta ou handoff.")
        if self.action == DecisionAction.NO_ACTION and (self.clarification is not None or self.clear_clarification):
            raise ValueError("NO_ACTION não pode alterar clarification.")
        if self.clarification is not None and self.clear_clarification:
            raise ValueError("Uma decisão não pode definir e limpar clarification ao mesmo tempo.")
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


def clarification_from_context(context):
    if not isinstance(context, dict):
        return None
    v2 = context.get("conversation_v2")
    raw = v2.get("clarification") if isinstance(v2, dict) else None
    try:
        return ClarificationState.model_validate(raw) if raw is not None else None
    except ValidationError:
        return None


def _focus_from_context(context):
    if not isinstance(context, dict):
        return ProductFocus()
    v2 = context.get("conversation_v2")
    raw = v2.get("focus") if isinstance(v2, dict) else None
    if raw is None:
        raw = {
            "product_ids": context.get("product_ids", []),
            "selected_product_id": context.get("selected_product_id"),
        }
    try:
        return ProductFocus.model_validate(raw)
    except ValidationError:
        return ProductFocus()


def _preferences_from_filters(filters):
    if not isinstance(filters, dict):
        return ConversationPreferences()
    values = {
        "garment": filters.get("garment"),
        "style_query": filters.get("query"),
        "size": filters.get("size"),
        "color": filters.get("color"),
        "max_price": filters.get("max_price"),
        "product_type": filters.get("product_type"),
        "offer_only": filters.get("offer_active"),
    }
    try:
        return ConversationPreferences.model_validate({key: value for key, value in values.items() if value is not None})
    except ValidationError:
        # Validate fields independently so one bad legacy/provider value does not
        # discard other safe preferences.
        safe = {}
        for key, value in values.items():
            if value is None:
                continue
            try:
                safe[key] = ConversationPreferences.model_validate({key: value}).model_dump(exclude_none=True)[key]
            except (ValidationError, KeyError):
                continue
        return ConversationPreferences.model_validate(safe)


def _preferences_from_context(context):
    if not isinstance(context, dict):
        return ConversationPreferences()
    v2 = context.get("conversation_v2")
    raw = v2.get("preferences") if isinstance(v2, dict) else None
    if raw is not None:
        try:
            return ConversationPreferences.model_validate(raw)
        except ValidationError:
            pass
    return _preferences_from_filters(context.get("filters"))


def _preferences_to_filters(preferences):
    values = preferences.model_dump(exclude_none=True)
    filters = {key: values[key] for key in ("garment", "size", "color", "max_price", "product_type")
               if key in values}
    if values.get("style_query"):
        filters["query"] = values["style_query"]
    if "offer_only" in values:
        filters["offer_active"] = values["offer_only"]
    return filters


def _preferences_for_message(current, message):
    text = normalize(message)
    values = current.model_dump(exclude_none=True)
    garment = next((piece for piece in PIECES if re.search(rf"\b{piece}s?\b", text)), None)
    if garment and values.get("garment") not in {None, garment}:
        values = {}
    if garment:
        values["garment"] = garment
    style = next((canonical for word, canonical in STYLE_TERMS.items()
                  if re.search(rf"\b{word}\b", text)), None)
    color = next((canonical for word, canonical in COLORS.items()
                  if re.search(rf"\b{word}\b", text)), None)
    size = re.search(r"\b(?:tamanho\s*)?(pp|xxg|xg|gg|p|m|g)\b|\btamanho\s*(3[4-9]|[45][0-9]|60)\b", text)
    price = re.search(r"(?:ate|no maximo|menos de)\s*(?:r\$\s*)?(\d{1,6}(?:[.,]\d{1,2})?)", text)
    if style:
        values["style_query"] = style
    if color:
        values["color"] = color
    if size:
        values["size"] = (size.group(1) or size.group(2)).upper()
    if price:
        values["max_price"] = float(price.group(1).replace(",", "."))
    if re.search(r"\b(oferta|ofertas|promocao|promocoes)\b", text):
        values["offer_only"] = True
    for word, product_type in (("brecho", "brecho"), ("drop", "drop"), ("drops", "drop")):
        if re.search(rf"\b{word}\b", text):
            values["product_type"] = product_type
    if re.search(r"\b(sem limite|qualquer preco)\b", text):
        values.pop("max_price", None)
    if re.search(r"\b(qualquer cor|outras cores)\b", text):
        values.pop("color", None)
    if re.search(r"\b(?:nao precisa ser|nao precisa de|sem preferencia de)\s+(?:da cor\s+)?(?:preto|preta|branco|branca|azul|vermelho|vermelha|roxo|roxa|rosa|cinza|verde|amarelo|amarela|laranja|bege|marrom)\b", text):
        values.pop("color", None)
    if re.search(r"\b(qualquer tamanho|outros tamanhos)\b", text):
        values.pop("size", None)
    if re.search(r"\b(sem oferta|fora da oferta|sem promocao)\b", text):
        values.pop("offer_only", None)
    return ConversationPreferences.model_validate(values)


def _discovery_question(preferences, message):
    """Ask one useful commercial question without consuming clarification attempts."""
    text = normalize(message)
    discovery_intent = wants_products(text) or bool(re.search(
        r"\b(?:quero|procuro|busco|gostaria de)\b.*\b(?:algo|roupa|peca|modelo|"
        + "|".join(STYLE_TERMS) + r")\b", text
    ))
    if not discovery_intent:
        return None
    if not preferences.garment:
        return "Claro 🖤 Você procura camiseta, cropped, calça, saia ou outro tipo de peça?"
    discriminators = (
        preferences.style_query, preferences.size, preferences.color,
        preferences.max_price, preferences.product_type, preferences.offer_only,
    )
    if not any(value is not None for value in discriminators):
        return "Claro 🖤 Qual tamanho, cor ou estilo você procura?"
    if not preferences.size and (preferences.style_query or preferences.color):
        return "Perfeito 🖤 Qual tamanho você procura?"
    return None


def _focus_for_message(current, message):
    text = normalize(message)
    ids = current.product_ids
    ordinal_patterns = [
        (r"\b(?:primeira|primeiro)\b", 0),
        (r"\b(?:segunda|segundo)\b", 1),
        (r"\b(?:terceira|terceiro)\b", 2),
        (r"\b(?:ultima|ultimo)\b", len(ids) - 1),
    ]
    for pattern, index in ordinal_patterns:
        if re.search(pattern, text):
            if 0 <= index < len(ids):
                return current.model_copy(update={"selected_product_id": ids[index]}), False
            return current, True
    contextual_reference = bool(re.search(
        r"\b(?:essa|esse|esta|este|aquela|aquele|ela|ele)\b|\b(?:outra|outro)\s+(?:parecida|parecido|semelhante)\b|"
        r"\ba\s+(?:pp|xxg|xg|gg|p|m|g|3[4-9]|[45][0-9]|60)\b", text
    ))
    if not contextual_reference:
        return current, False
    if current.selected_product_id:
        return current, False
    if len(ids) == 1:
        return current.model_copy(update={"selected_product_id": ids[0]}), False
    return current, True


def _prepared_context(current, message):
    """Build small structured memory and compatibility inputs for the shared agent."""
    context = {key: value for key, value in (current if isinstance(current, dict) else {}).items()
               if key != "suggestion_cache"}
    preferences = _preferences_for_message(_preferences_from_context(context), message)
    focus, ambiguous_reference = _focus_for_message(_focus_from_context(context), message)
    context["filters"] = _preferences_to_filters(preferences)
    context["product_ids"] = focus.product_ids
    if focus.selected_product_id:
        context["selected_product_id"] = focus.selected_product_id
    else:
        context.pop("selected_product_id", None)
    return context, preferences, focus, ambiguous_reference


def clear_clarification_context(current):
    """Remove only active clarification state, without disturbing other context."""
    if not isinstance(current, dict):
        return {}
    context = dict(current)
    existing_v2 = context.get("conversation_v2")
    if not isinstance(existing_v2, dict) or "clarification" not in existing_v2:
        return context
    v2 = dict(existing_v2)
    v2.pop("clarification", None)
    context["conversation_v2"] = v2
    return context


def change_mode(db, conversation_id, mode):
    from services.whatsapp_inbox_service import require_conversation
    from services.whatsapp_hybrid_service import handoff
    c = require_conversation(db, conversation_id, lock=True)
    if mode != "OFF" and not settings.AI_WHATSAPP_ENABLED:
        raise SupportError("Ative AI_WHATSAPP_ENABLED no servidor primeiro.", 409)
    c.ai_mode = mode
    c.version += 1
    c.context = {k: v for k, v in (c.context or {}).items() if k != "suggestion_cache"}
    if mode != "AUTO":
        c.context = clear_clarification_context(c.context)
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


def _hard_handoff_reason(text, context=None):
    text = normalize(text)
    pending = clarification_from_context(context)
    process_topic_selection = bool(
        pending and _process_topic_message(text)
    )
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
    return next((HandoffReason(reason) for reason, pattern in patterns
                 if not (process_topic_selection and reason == "RETURN_EXCHANGE")
                 and re.search(pattern, text)), None)


def hard_handoff_decision(text, context=None):
    """Apply critical deterministic rules before any LLM or catalog planning."""
    reason = _hard_handoff_reason(text, context)
    if reason is None:
        return None
    return WhatsAppDecision(
        action=DecisionAction.HANDOFF,
        handoff_reason=reason,
        reason_code=reason.value,
        clear_clarification=clarification_from_context(context) is not None,
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


def _process_topic_message(text):
    text = normalize(text).strip(" .,!?:;")
    topics = [
        (r"(?:sobre )?compras?", "Como funciona a compra?"),
        (r"(?:sobre )?entregas?", "Como é feita a entrega?"),
        (r"(?:sobre )?(?:troca|trocas|devolucao|devolucoes|troca e devolucao)",
         "Como funciona a troca ou devolução?"),
        (r"(?:sobre )?atendimento", "Como funciona o chat?"),
        (r"(?:sobre )?(?:catalogo|pecas|produtos)", "Como funciona o catálogo?"),
    ]
    return next((message for pattern, message in topics if re.fullmatch(pattern, text)), None)


def _clarification_kind(decision, pending):
    if pending:
        return pending.kind
    return "PROCESS_TOPIC" if decision.reason_code == "AMBIGUOUS_PROCESS" else "GENERAL"


def _clarification_prompt(kind, attempts, response):
    if kind == "PROCESS_TOPIC":
        return PROCESS_TOPIC_PROMPTS[attempts]
    return response.message if attempts == 1 else GENERAL_CLARIFICATION_PROMPT


def _advance_clarification(decision, pending):
    if decision.action == DecisionAction.NO_ACTION:
        return decision
    if decision.action == DecisionAction.CLARIFY:
        attempts = (pending.attempts if pending else 0) + 1
        if attempts > MAX_CLARIFICATION_ATTEMPTS:
            return WhatsAppDecision(
                action=DecisionAction.HANDOFF,
                handoff_reason=HandoffReason.LOW_CONFIDENCE,
                reason_code="CLARIFICATION_EXHAUSTED",
                clarification=pending,
            )
        kind = _clarification_kind(decision, pending)
        response = decision.response.model_copy(update={
            "message": _clarification_prompt(kind, attempts, decision.response),
        })
        return decision.model_copy(update={
            "response": response,
            "clarification": ClarificationState(
                attempts=attempts,
                kind=kind,
                options=list(PROCESS_TOPIC_OPTIONS),
            ),
        })
    if pending:
        return decision.model_copy(update={"clear_clarification": True})
    return decision


def decide(db, incoming):
    """Resolve one WhatsApp turn into a validated operational decision."""
    pending = clarification_from_context(incoming.context)
    hard_handoff = hard_handoff_decision(incoming.message, incoming.context)
    if hard_handoff:
        return hard_handoff
    prepared_context, preferences, focus, ambiguous_reference = _prepared_context(
        incoming.context, incoming.message
    )
    context_patch = {
        "preferences": preferences.model_dump(exclude_none=True),
        "focus": focus.model_dump(mode="json"),
    }
    if ambiguous_reference:
        decision = WhatsAppDecision(
            action=DecisionAction.CLARIFY,
            response=AgentResponse(
                message="Qual produto você quis dizer? Pode indicar a primeira, segunda, terceira ou enviar o nome da peça.",
                decision_hint="CLARIFY",
                decision_reason_code="AMBIGUOUS_PRODUCT_REFERENCE",
            ),
            reason_code="AMBIGUOUS_PRODUCT_REFERENCE",
            context_patch=context_patch,
        )
        return _advance_clarification(decision, pending)
    discovery_question = _discovery_question(preferences, incoming.message)
    if discovery_question:
        decision = WhatsAppDecision(
            action=DecisionAction.ANSWER,
            response=AgentResponse(message=discovery_question),
            reason_code="PREFERENCE_SLOT_REQUESTED",
            context_patch=context_patch,
        )
        return _advance_clarification(decision, pending)
    effective_incoming = incoming.model_copy(update={"context": prepared_context})
    if pending:
        resolved_message = _process_topic_message(incoming.message)
        if resolved_message:
            effective_incoming = effective_incoming.model_copy(update={"message": resolved_message})
    try:
        decision = decision_from_agent_response(ai_agent.respond(db, effective_incoming))
    except Exception:
        logger.warning("whatsapp_ai_decision_failed conversation_id=%s", incoming.conversation_id)
        decision = WhatsAppDecision(
            action=DecisionAction.HANDOFF,
            handoff_reason=HandoffReason.AI_FAILURE,
            reason_code="AGENT_EXCEPTION",
            failure_kind="AGENT_EXCEPTION",
        )
    decision = decision.model_copy(update={
        "context_patch": {**context_patch, **decision.context_patch},
    })
    return _advance_clarification(decision, pending)


def context_after_decision(current, decision, source_message_id):
    """Persist the minimal versioned V2 state while keeping legacy context compatible."""
    context = {key: value for key, value in (current if isinstance(current, dict) else {}).items()
               if key != "suggestion_cache"}
    response_patch = _agent_context_patch(decision.response) if decision.response else {}
    legacy_patch = {key: value for key, value in decision.context_patch.items()
                    if key in {"filters", "product_ids", "pending_correction"}}
    response_patch.update(legacy_patch)
    if "pending_correction" in response_patch:
        context["pending_correction"] = response_patch["pending_correction"]

    preferences = _preferences_from_context(context)
    if "preferences" in decision.context_patch:
        try:
            preferences = ConversationPreferences.model_validate(decision.context_patch["preferences"])
        except ValidationError:
            pass
    if "filters" in response_patch:
        preferences = _preferences_from_filters(response_patch["filters"])

    focus = _focus_from_context(context)
    if "focus" in decision.context_patch:
        try:
            focus = ProductFocus.model_validate(decision.context_patch["focus"])
        except ValidationError:
            pass
    response_ids = None
    if decision.response and decision.response.products:
        response_ids = [product.id for product in decision.response.products]
    elif "product_ids" in response_patch:
        response_ids = response_patch["product_ids"]
    if response_ids is not None:
        ids = ProductFocus(product_ids=response_ids).product_ids
        selected = focus.selected_product_id if focus.selected_product_id in ids else None
        if selected is None and len(ids) == 1:
            selected = ids[0]
        focus = ProductFocus(product_ids=ids, selected_product_id=selected)

    # Root mirrors keep F2A/F2B and the shared agent compatible; V2 is canonical.
    context["filters"] = _preferences_to_filters(preferences)
    context["product_ids"] = focus.product_ids
    if focus.selected_product_id:
        context["selected_product_id"] = focus.selected_product_id
    else:
        context.pop("selected_product_id", None)
    existing_v2 = context.get("conversation_v2")
    v2 = dict(existing_v2) if isinstance(existing_v2, dict) else {}
    v2["schema_version"] = 1
    v2["focus"] = focus.model_dump(mode="json")
    v2["preferences"] = preferences.model_dump(exclude_none=True)
    if decision.clear_clarification:
        v2.pop("clarification", None)
    elif decision.clarification:
        clarification = decision.clarification.model_dump(mode="json")
        if decision.action == DecisionAction.CLARIFY or not clarification.get("source_message_id"):
            clarification["source_message_id"] = str(source_message_id)[:80]
        v2["clarification"] = clarification
    v2["last_decision"] = {
        "action": decision.action.value,
        "reason_code": decision.reason_code,
        "source_message_id": str(source_message_id)[:80],
    }
    context["conversation_v2"] = v2
    return context


def build_whatsapp_agent_input(db, conversation, source=None):
    """Build a bounded, current-cycle input; messages remain untrusted conversation data."""
    cycle_filter = or_(Message.extra_data["cycle"].as_integer() == conversation.cycle,
                       (Message.extra_data["cycle"].as_integer().is_(None)) if conversation.cycle == 1 else False)
    source = source or db.scalar(select(Message).where(Message.conversation_id == conversation.id,
        Message.sender == "customer", cycle_filter
    ).order_by(Message.created_at.desc(), Message.id.desc()).limit(1))
    if not source:
        raise SupportError("Não há mensagem do cliente neste ciclo.", 409)
    history_limit = min(settings.CHAT_HISTORY_MESSAGES, WHATSAPP_CONTEXT_HISTORY_LIMIT)
    rows = db.scalars(select(Message).where(Message.conversation_id == conversation.id,
        Message.id != source.id,
        Message.sender.in_(["customer", "assistant", "human"]),
        or_(Message.sender == "customer", Message.extra_data["delivery_status"].as_string() == "sent",
            Message.extra_data["delivery_status"].as_string().is_(None)),
        cycle_filter
    ).order_by(Message.created_at.desc(), Message.id.desc()).limit(history_limit)).all()
    context, _, _, _ = _prepared_context(conversation.context, source.content)
    context.update(status=conversation.status, ai_mode=conversation.ai_mode, handoff_reason=conversation.handoff_reason)
    return AgentInput(channel="whatsapp", conversation_id=conversation.id, customer_id=conversation.customer_id,
        message=source.content[:2000], history=[HistoryEntry(sender=m.sender, content=m.content[:1000])
        for m in reversed(rows)], context=context)


def agent_input(db, conversation, source=None):
    """Compatibility alias for the explicit WhatsApp context builder."""
    return build_whatsapp_agent_input(db, conversation, source)


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
