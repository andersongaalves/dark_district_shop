from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from models.atendimento import HandoffReason
from schemas.atendimento import AgentInput, AgentResponse
from services import whatsapp_ai_service as ai


def incoming(message, context=None):
    return AgentInput(
        channel="whatsapp",
        conversation_id="conversation-test",
        customer_id="customer-test",
        message=message,
        context=context or {},
    )


def test_ambiguous_process_question_is_structured_clarification(db):
    decision = ai.decide(db, incoming("Como funcionam os processos?"))

    assert decision.action == ai.DecisionAction.CLARIFY
    assert decision.handoff_reason is None
    assert decision.reason_code == "AMBIGUOUS_PROCESS"
    assert decision.clarification.attempts == 1
    assert decision.clarification.kind == "PROCESS_TOPIC"
    assert "Qual processo você quer conhecer melhor?" in decision.response.message


def test_clarification_reaches_second_prompt_then_low_confidence(db):
    first = ai.decide(db, incoming("Como funcionam os processos?"))
    first_context = ai.context_after_decision({}, first, "message-1")

    second = ai.decide(db, incoming("Sei lá, os processos.", first_context))
    second_context = ai.context_after_decision(first_context, second, "message-2")

    exhausted = ai.decide(db, incoming("Não sei explicar.", second_context))
    exhausted_context = ai.context_after_decision(second_context, exhausted, "message-3")

    assert second.action == ai.DecisionAction.CLARIFY
    assert second.clarification.attempts == 2
    assert second.response.message != first.response.message
    assert "antes de comprar" in second.response.message
    assert exhausted.action == ai.DecisionAction.HANDOFF
    assert exhausted.handoff_reason == HandoffReason.LOW_CONFIDENCE
    assert exhausted_context["conversation_v2"]["clarification"]["attempts"] == 2
    assert exhausted_context["conversation_v2"]["last_decision"]["action"] == "HANDOFF"


@pytest.mark.parametrize("answer", ["Compra", "Entrega", "Troca", "Atendimento", "Catálogo"])
def test_clarification_resolves_an_allowlisted_topic_and_resets(db, answer):
    first = ai.decide(db, incoming("Como funcionam os processos?"))
    context = ai.context_after_decision({}, first, "message-1")

    resolved = ai.decide(db, incoming(answer, context))
    resolved_context = ai.context_after_decision(context, resolved, "message-2")

    assert resolved.action == ai.DecisionAction.ANSWER
    assert resolved.clear_clarification
    assert "clarification" not in resolved_context["conversation_v2"]
    assert resolved_context["conversation_v2"]["last_decision"]["action"] == "ANSWER"


def test_clarification_can_resolve_after_second_prompt(db):
    first = ai.decide(db, incoming("Como funcionam os processos?"))
    context = ai.context_after_decision({}, first, "message-1")
    second = ai.decide(db, incoming("Não sei", context))
    context = ai.context_after_decision(context, second, "message-2")

    resolved = ai.decide(db, incoming("Entrega", context))
    context = ai.context_after_decision(context, resolved, "message-3")

    assert resolved.action == ai.DecisionAction.ANSWER
    assert "clarification" not in context["conversation_v2"]


@pytest.mark.parametrize(("message", "reason"), [
    ("Quero falar com uma pessoa", HandoffReason.HUMAN_REQUESTED),
    ("Quero comprar essa", HandoffReason.PURCHASE_INTENT),
    ("Como faço o PIX?", HandoffReason.PAYMENT),
    ("Meu pedido não chegou", HandoffReason.DELIVERY_ISSUE),
    ("Quero devolver", HandoffReason.RETURN_EXCHANGE),
    ("Tenho uma reclamação", HandoffReason.COMPLAINT),
    ("Pode fazer desconto?", HandoffReason.NEGOTIATION),
])
def test_hard_handoffs_run_before_agent(db, monkeypatch, message, reason):
    monkeypatch.setattr(ai.ai_agent, "respond", lambda *_: pytest.fail("agent must not run"))

    decision = ai.decide(db, incoming(message))

    assert decision.action == ai.DecisionAction.HANDOFF
    assert decision.handoff_reason == reason


@pytest.mark.parametrize(("message", "reason"), [
    ("Na verdade quero falar com uma pessoa", HandoffReason.HUMAN_REQUESTED),
    ("Quero comprar aquela camiseta", HandoffReason.PURCHASE_INTENT),
    ("Como faço o PIX?", HandoffReason.PAYMENT),
])
def test_hard_handoff_interrupts_and_clears_clarification(db, monkeypatch, message, reason):
    first = ai.decide(db, incoming("Como funcionam os processos?"))
    context = ai.context_after_decision({}, first, "message-1")
    monkeypatch.setattr(ai.ai_agent, "respond", lambda *_: pytest.fail("agent must not run"))

    handoff = ai.decide(db, incoming(message, context))
    final_context = ai.context_after_decision(context, handoff, "message-2")

    assert handoff.action == ai.DecisionAction.HANDOFF
    assert handoff.handoff_reason == reason
    assert "clarification" not in final_context["conversation_v2"]


def test_hard_handoff_preserves_product_context_for_human(db):
    context = {
        "conversation_v2": {
            "schema_version": 1,
            "focus": {"product_ids": ["product-a"], "selected_product_id": "product-a"},
            "preferences": {"size": "M", "color": "preto"},
        },
    }

    decision = ai.decide(db, incoming("Quero comprar essa", context))
    final_context = ai.context_after_decision(context, decision, "message-1")

    assert decision.handoff_reason == HandoffReason.PURCHASE_INTENT
    assert final_context["conversation_v2"]["focus"]["selected_product_id"] == "product-a"
    assert final_context["conversation_v2"]["preferences"] == {"size": "M", "color": "preto"}


def test_clear_supported_question_is_answer(db):
    decision = ai.decide(db, incoming("Como funciona a compra?"))

    assert decision.action == ai.DecisionAction.ANSWER
    assert decision.response.message
    assert decision.handoff_reason is None


@pytest.mark.parametrize(("mode", "status", "reason"), [
    ("OFF", "AI", "AI_MODE_OFF"),
    ("ASSIST", "AI", "AI_MODE_ASSIST"),
    ("AUTO", "HUMAN", "STATUS_HUMAN"),
    ("AUTO", "WAITING_HUMAN", "STATUS_WAITING_HUMAN"),
])
def test_non_auto_states_produce_no_action(mode, status, reason):
    decision = ai.auto_state_decision(SimpleNamespace(ai_mode=mode, status=status))

    assert decision.action == ai.DecisionAction.NO_ACTION
    assert decision.reason_code == reason
    assert decision.response is None


def test_invalid_agent_response_fails_safely(db, monkeypatch):
    monkeypatch.setattr(ai.ai_agent, "respond", lambda *_: {"message": "Fechei a compra", "type": "purchase"})

    decision = ai.decide(db, incoming("Mensagem não classificada"))

    assert decision.action == ai.DecisionAction.HANDOFF
    assert decision.handoff_reason == HandoffReason.AI_FAILURE
    assert decision.response is None


def test_technical_failure_during_clarification_is_not_low_confidence(db, monkeypatch):
    first = ai.decide(db, incoming("Como funcionam os processos?"))
    context = ai.context_after_decision({}, first, "message-1")
    monkeypatch.setattr(ai.ai_agent, "respond", lambda *_: AgentResponse(
        message="Falha temporária", type="error"
    ))

    failure = ai.decide(db, incoming("Ainda não sei", context))
    final_context = ai.context_after_decision(context, failure, "message-2")

    assert failure.action == ai.DecisionAction.HANDOFF
    assert failure.handoff_reason == HandoffReason.AI_FAILURE
    assert failure.handoff_reason != HandoffReason.LOW_CONFIDENCE
    assert "clarification" not in final_context["conversation_v2"]


def test_decision_model_rejects_inconsistent_payload():
    with pytest.raises(ValidationError):
        ai.WhatsAppDecision(action="HANDOFF", reason_code="MISSING_REASON")
    with pytest.raises(ValidationError):
        ai.WhatsAppDecision(
            action="NO_ACTION",
            reason_code="BLOCKED",
            response=AgentResponse(message="should not be sent"),
        )


def test_old_or_empty_context_accepts_last_decision():
    response = AgentResponse(message="Resposta segura", context={"filters": {"size": "M"}})
    decision = ai.decision_from_agent_response(response)

    empty = ai.context_after_decision(None, decision, "message-1")
    legacy = ai.context_after_decision({"legacy": True, "suggestion_cache": {"old": True}}, decision, "message-2")

    assert empty["conversation_v2"] == {
        "schema_version": 1,
        "focus": {"product_ids": [], "selected_product_id": None},
        "preferences": {"size": "M"},
        "last_decision": {
            "action": "ANSWER",
            "reason_code": "SUPPORTED_RESPONSE",
            "source_message_id": "message-1",
        },
    }
    assert empty["filters"] == {"size": "M"}
    assert legacy["legacy"] is True
    assert "suggestion_cache" not in legacy


def test_f2a_context_lazily_adds_clarification(db):
    context = {
        "conversation_v2": {
            "schema_version": 1,
            "last_decision": {
                "action": "ANSWER",
                "reason_code": "SUPPORTED_RESPONSE",
                "source_message_id": "old-message",
            },
        },
    }

    decision = ai.decide(db, incoming("Como funcionam os processos?", context))
    updated = ai.context_after_decision(context, decision, "new-message")

    assert updated["conversation_v2"]["clarification"]["attempts"] == 1
    assert updated["conversation_v2"]["clarification"]["source_message_id"] == "new-message"


def test_preferences_are_allowlisted_and_updated_across_turns(db):
    first = ai.decide(db, incoming("Quero uma camiseta dark preta, M, até 80"))
    context = ai.context_after_decision({}, first, "message-1")

    assert context["conversation_v2"]["preferences"] == {
        "garment": "camiseta", "style_query": "dark", "size": "M",
        "color": "preto", "max_price": 80.0,
    }

    second = ai.decide(db, incoming("Pode ser G também", context))
    context = ai.context_after_decision(context, second, "message-2")

    assert context["conversation_v2"]["preferences"]["size"] == "G"
    assert context["conversation_v2"]["preferences"]["color"] == "preto"


@pytest.mark.parametrize(("message", "expected", "preferences"), [
    ("Quero camiseta", "Qual tamanho, cor ou estilo", {"garment": "camiseta"}),
    ("Quero algo gótico", "Você procura camiseta", {"style_query": "gotico"}),
])
def test_discovery_questions_are_answers_not_clarification(db, message, expected, preferences):
    decision = ai.decide(db, incoming(message))
    context = ai.context_after_decision({}, decision, "message-1")

    assert decision.action == ai.DecisionAction.ANSWER
    assert decision.reason_code == "PREFERENCE_SLOT_REQUESTED"
    assert expected in decision.response.message
    assert "clarification" not in context["conversation_v2"]
    assert context["conversation_v2"]["preferences"] == preferences


def test_explicit_filters_skip_discovery_question_and_color_can_be_relaxed(db):
    first = ai.decide(db, incoming("Quero camiseta preta M até 80"))
    context = ai.context_after_decision({}, first, "message-1")

    assert first.action == ai.DecisionAction.ANSWER
    assert first.reason_code == "SUPPORTED_RESPONSE"
    assert context["conversation_v2"]["preferences"]["color"] == "preto"

    relaxed = ai.decide(db, incoming("Não precisa ser preta", context))
    context = ai.context_after_decision(context, relaxed, "message-2")

    assert relaxed.action == ai.DecisionAction.ANSWER
    assert "color" not in context["conversation_v2"]["preferences"]
    assert "clarification" not in context["conversation_v2"]


def test_product_ordinals_update_focus_deterministically(db, monkeypatch):
    seen = []

    def respond(_db, request):
        seen.append(request.context)
        return AgentResponse(message="Produto consultado", context=request.context)

    monkeypatch.setattr(ai.ai_agent, "respond", respond)
    context = {"conversation_v2": {
        "schema_version": 1,
        "focus": {"product_ids": ["product-a", "product-b", "product-c"], "selected_product_id": None},
        "preferences": {},
    }}

    second = ai.decide(db, incoming("Gostei da segunda", context))
    second_context = ai.context_after_decision(context, second, "message-1")
    last = ai.decide(db, incoming("A última", context))
    last_context = ai.context_after_decision(context, last, "message-2")

    assert seen[0]["selected_product_id"] == "product-b"
    assert second_context["conversation_v2"]["focus"]["selected_product_id"] == "product-b"
    assert seen[1]["selected_product_id"] == "product-c"
    assert last_context["conversation_v2"]["focus"]["selected_product_id"] == "product-c"


def test_ambiguous_product_reference_without_focus_clarifies(db, monkeypatch):
    monkeypatch.setattr(ai.ai_agent, "respond", lambda *_: pytest.fail("agent must not guess"))

    decision = ai.decide(db, incoming("Tem essa em M?"))

    assert decision.action == ai.DecisionAction.CLARIFY
    assert decision.reason_code == "AMBIGUOUS_PRODUCT_REFERENCE"


def test_product_focus_is_bounded_and_deduplicated():
    focus = ai.ProductFocus(product_ids=["same", "same", *[f"product-{index}" for index in range(20)]])

    assert focus.product_ids == ["same", *[f"product-{index}" for index in range(9)]]
    assert len(focus.product_ids) == ai.MAX_FOCUS_PRODUCTS


def test_webchat_response_contract_does_not_expose_decision_hint(db):
    web_input = incoming("Como funcionam os processos?").model_copy(update={"channel": "web"})
    response = ai.ai_agent.respond(db, web_input)

    assert response.type == "message"
    assert response.decision_hint == "CLARIFY"
    assert "decision_hint" not in response.model_dump()
    assert "decision_reason_code" not in response.model_dump()
