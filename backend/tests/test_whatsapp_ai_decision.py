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
    assert "Qual processo você quer conhecer melhor?" in decision.response.message


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

    empty = ai.context_after_decision({}, decision, "message-1")
    legacy = ai.context_after_decision({"legacy": True, "suggestion_cache": {"old": True}}, decision, "message-2")

    assert empty["conversation_v2"] == {
        "schema_version": 1,
        "last_decision": {
            "action": "ANSWER",
            "reason_code": "SUPPORTED_RESPONSE",
            "source_message_id": "message-1",
        },
    }
    assert empty["filters"] == {"size": "M"}
    assert legacy["legacy"] is True
    assert "suggestion_cache" not in legacy


def test_webchat_response_contract_does_not_expose_decision_hint(db):
    web_input = incoming("Como funcionam os processos?").model_copy(update={"channel": "web"})
    response = ai.ai_agent.respond(db, web_input)

    assert response.type == "message"
    assert response.decision_hint == "CLARIFY"
    assert "decision_hint" not in response.model_dump()
    assert "decision_reason_code" not in response.model_dump()
