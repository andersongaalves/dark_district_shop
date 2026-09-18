from datetime import timedelta
from uuid import uuid4
from types import SimpleNamespace
import pytest
from sqlalchemy.orm import sessionmaker
from models.atendimento import Conversation, Message, DeliveryJob, utc_now
from channels.whatsapp_channel import IncomingText
from core.config import settings
from services import whatsapp_hybrid_service as hybrid, whatsapp_ai_service as ai, conversation_service
from integrations.whatsapp.client import WhatsAppDeliveryError
from integrations.llm.provider import Plan, ToolCall
from test_catalog_tools import create_product


@pytest.fixture
def flow(db, monkeypatch):
    for key, value in {"AI_WHATSAPP_ENABLED": True, "WHATSAPP_ENABLED": True,
        "WHATSAPP_AI_DEFAULT_MODE": "AUTO", "WHATSAPP_PHONE_NUMBER_ID": "1234567",
        "WHATSAPP_ATTENDANT_NUMBER": "5511999990000"}.items():
        monkeypatch.setattr(settings, key, value)
    sent, notified = [], []
    monkeypatch.setattr(hybrid, "send_text", lambda recipient, text: sent.append((recipient, text)) or "wamid.sent")
    monkeypatch.setattr(hybrid.notifications, "deliver", lambda db, payload: notified.append(payload) or "wamid.notification")
    sessions = sessionmaker(bind=db.get_bind(), autoflush=False)
    def receive(text, identifier=None):
        item = IncomingText("1234567", "557400000000", identifier or str(uuid4()), text, int(utc_now().timestamp()))
        hybrid.receive_messages(db, [item])
        return item
    def drain():
        for _ in range(30):
            if not hybrid.run_once(sessions):
                break
        else:
            pytest.fail("Queue did not drain")
        db.expire_all()
    return SimpleNamespace(receive=receive, drain=drain, sent=sent, notified=notified, sessions=sessions)


def test_auto_uses_real_catalog_without_mutating_stock(client, db, flow):
    create_product(client)
    item = flow.receive("Tem camiseta preta M?")
    flow.receive(item.text, item.message_id)
    assert not flow.sent  # webhook does not call LLM/Meta
    flow.drain()
    assert len(flow.sent) == 2
    assert "R$ 99,90" in flow.sent[-1][1] and "M / Preto: 5 un." in flow.sent[-1][1]
    flow.receive("Tem saia azul GG?")
    flow.drain()
    assert "Não encontrei saias" in flow.sent[-1][1]
    assert not flow.notified


def test_multiturn_size_answer_uses_current_preferences(client, db, flow):
    create_product(client, title="Camiseta Oversized")

    flow.receive("Tem camiseta oversized?")
    flow.drain()
    assert flow.sent[-1][1] == "Qual tamanho você procura?"

    flow.receive("M")
    flow.drain()

    conversation = db.query(Conversation).one()
    preferences = conversation.context["conversation_v2"]["preferences"]
    assert preferences == {"garment": "camiseta", "style_query": "oversized", "size": "M"}
    assert conversation.context["conversation_v2"]["last_decision"]["action"] == "ANSWER"
    assert "Camiseta Oversized" in flow.sent[-1][1]


def test_selected_product_stays_in_focus_for_color_size_and_price(client, db, flow):
    create_product(client, id="prod-001", title="Produto A", price=100)
    create_product(client, id="prod-002", title="Produto B", price=79)
    create_product(client, id="prod-003", title="Produto C", price=120)

    first = flow.receive("Mostre as peças disponíveis")
    flow.receive(first.text, first.message_id)
    flow.drain()
    conversation = db.query(Conversation).one()
    presented = conversation.context["conversation_v2"]["focus"]["product_ids"]
    assert len(presented) == 3
    assert presented[1] == "prod-002"

    flow.receive("Gostei da segunda")
    flow.drain()
    assert conversation.context["conversation_v2"]["focus"]["selected_product_id"] == "prod-002"

    flow.receive("Tem essa em M?")
    flow.drain()
    flow.receive("E preta?")
    flow.drain()
    assert conversation.context["conversation_v2"]["preferences"]["size"] == "M"
    assert conversation.context["conversation_v2"]["preferences"]["color"] == "preto"

    flow.receive("Quanto fica?")
    flow.drain()
    assert "Produto B" in flow.sent[-1][1]
    assert "R$ 79,00" in flow.sent[-1][1]

    flow.receive("Tem outra parecida?")
    flow.drain()
    assert conversation.status == "AI"
    assert conversation.context["conversation_v2"]["focus"]["selected_product_id"] == "prod-002"


def test_context_history_is_limited_to_twelve_messages_in_current_cycle(db, flow):
    for index in range(15):
        flow.receive(f"mensagem {index}")

    conversation = db.query(Conversation).one()
    request = ai.build_whatsapp_agent_input(db, conversation)

    assert len(request.history) == ai.WHATSAPP_CONTEXT_HISTORY_LIMIT
    assert request.message == "mensagem 14"
    assert request.history[0].content == "mensagem 2"
    assert request.history[-1].content == "mensagem 13"


def test_ambiguous_process_clarifies_once_without_handoff(db, flow):
    item = flow.receive("Como funcionam os processos?")
    flow.receive(item.text, item.message_id)
    flow.drain()

    conversation = db.query(Conversation).one()
    assert conversation.status == "AI"
    assert conversation.handoff_reason is None
    assert conversation.context["conversation_v2"]["last_decision"]["action"] == "CLARIFY"
    assert conversation.context["conversation_v2"]["clarification"]["attempts"] == 1
    assert len(flow.notified) == 0
    assert len(flow.sent) == 2
    assert "Qual processo você quer conhecer melhor?" in flow.sent[-1][1]


def test_clarification_sequence_handoffs_only_after_two_questions(db, flow):
    flow.receive("Como funcionam os processos?")
    flow.drain()
    conversation = db.query(Conversation).one()
    assert conversation.context["conversation_v2"]["clarification"]["attempts"] == 1

    flow.receive("Sei lá, os processos.")
    flow.drain()
    assert conversation.status == "AI"
    assert conversation.context["conversation_v2"]["clarification"]["attempts"] == 2
    assert "antes de comprar" in flow.sent[-1][1]

    flow.receive("Não sei explicar.")
    flow.drain()
    assert conversation.status == "WAITING_HUMAN"
    assert conversation.handoff_reason == "LOW_CONFIDENCE"
    assert conversation.context["conversation_v2"]["clarification"]["attempts"] == 2
    assert conversation.context["conversation_v2"]["last_decision"]["action"] == "HANDOFF"
    assert len(flow.notified) == 1
    assert len(flow.sent) == 4  # welcome, two questions, one handoff


def test_clarification_resolves_on_first_answer_and_stays_ai(db, flow):
    flow.receive("Como funcionam os processos?")
    flow.drain()
    flow.receive("Compra")
    flow.drain()

    conversation = db.query(Conversation).one()
    assert conversation.status == "AI"
    assert conversation.handoff_reason is None
    assert "clarification" not in conversation.context["conversation_v2"]
    assert conversation.context["conversation_v2"]["last_decision"]["action"] == "ANSWER"
    assert len(flow.notified) == 0


def test_clarification_resolves_on_second_answer_and_stays_ai(db, flow):
    for message in ["Como funcionam os processos?", "Não sei", "Entrega"]:
        flow.receive(message)
        flow.drain()

    conversation = db.query(Conversation).one()
    assert conversation.status == "AI"
    assert "clarification" not in conversation.context["conversation_v2"]
    assert conversation.context["conversation_v2"]["last_decision"]["action"] == "ANSWER"


def test_concurrent_ambiguous_messages_create_only_clarify_one(db, flow):
    flow.receive("Como funcionam os processos?")
    flow.receive("Ainda não sei explicar")
    flow.drain()

    conversation = db.query(Conversation).one()
    assert conversation.status == "AI"
    assert conversation.context["conversation_v2"]["clarification"]["attempts"] == 1
    assert conversation.context["conversation_v2"]["last_decision"]["action"] == "CLARIFY"
    assert len(flow.sent) == 2  # welcome plus the latest message's first clarification


def test_reprocessing_sent_inbound_does_not_advance_clarification(db, flow):
    flow.receive("Como funcionam os processos?")
    flow.drain()
    conversation = db.query(Conversation).one()
    job = db.query(DeliveryJob).filter(DeliveryJob.kind == "inbound").one()
    before = len(flow.sent)

    hybrid.process_auto(job, flow.sessions)
    db.expire_all()

    assert conversation.context["conversation_v2"]["clarification"]["attempts"] == 1
    assert len(flow.sent) == before


def test_clarification_resets_on_claim_and_closed_cycle(client, db, flow):
    flow.receive("Como funcionam os processos?")
    flow.drain()
    conversation = db.query(Conversation).one()
    assert client.post(f"/admin/conversations/{conversation.id}/claim").status_code == 200
    db.refresh(conversation)
    assert "clarification" not in conversation.context["conversation_v2"]

    ai.change_mode(db, conversation.id, "AUTO")
    conversation_service.change_status(db, conversation.id, "AI")
    flow.receive("Como funcionam os processos?")
    flow.drain()
    conversation_service.change_status(db, conversation.id, "CLOSED")
    assert "clarification" not in conversation.context["conversation_v2"]

    flow.receive("Como funcionam os processos?")
    flow.drain()
    assert conversation.cycle == 2
    assert conversation.context["conversation_v2"]["clarification"]["attempts"] == 1


def test_resume_after_low_confidence_starts_without_clarification(db, flow):
    for message in ["Como funcionam os processos?", "Não sei", "Ainda não sei"]:
        flow.receive(message)
        flow.drain()
    conversation = db.query(Conversation).one()
    assert conversation.handoff_reason == "LOW_CONFIDENCE"

    conversation_service.change_status(db, conversation.id, "AI")
    assert conversation.status == "AI"
    assert "clarification" not in conversation.context["conversation_v2"]


def test_waiting_human_message_does_not_advance_clarification(db, flow):
    for message in ["Como funcionam os processos?", "Não sei", "Ainda não sei"]:
        flow.receive(message)
        flow.drain()
    conversation = db.query(Conversation).one()
    before = len(flow.sent)

    flow.receive("Continuo sem saber")
    flow.drain()

    assert conversation.context["conversation_v2"]["clarification"]["attempts"] == 2
    assert len(flow.sent) == before


@pytest.mark.parametrize(("message", "reason"), [
    ("Quero falar com uma pessoa", "HUMAN_REQUESTED"),
    ("Quero comprar aquela camiseta", "PURCHASE_INTENT"),
    ("Como faço o PIX?", "PAYMENT"),
])
def test_hard_handoff_during_clarification_keeps_real_reason(db, flow, message, reason):
    flow.receive("Como funcionam os processos?")
    flow.drain()

    flow.receive(message)
    flow.drain()

    conversation = db.query(Conversation).one()
    assert conversation.status == "WAITING_HUMAN"
    assert conversation.handoff_reason == reason
    assert "clarification" not in conversation.context["conversation_v2"]
    assert conversation.context["conversation_v2"]["last_decision"]["reason_code"] == reason


def test_assist_suggestion_and_off_messages_do_not_create_clarification(client, db, flow, monkeypatch):
    from schemas.atendimento import AgentResponse

    flow.receive("Olá")
    flow.drain()
    conversation = db.query(Conversation).one()
    assert client.post(f"/admin/conversations/{conversation.id}/claim").status_code == 200

    monkeypatch.setattr(ai.ai_agent, "respond", lambda *_: AgentResponse(
        message="Qual assunto?", decision_hint="CLARIFY", decision_reason_code="AMBIGUOUS_MESSAGE"
    ))
    assert client.post(f"/admin/conversations/{conversation.id}/ai-suggestion", json={}).status_code == 200
    db.refresh(conversation)
    assert conversation.ai_mode == "ASSIST"
    assert "clarification" not in conversation.context.get("conversation_v2", {})

    ai.change_mode(db, conversation.id, "OFF")
    before = len(flow.sent)
    flow.receive("Como funcionam os processos?")
    flow.drain()
    assert "clarification" not in conversation.context.get("conversation_v2", {})
    assert len(flow.sent) == before


def test_invalid_structured_agent_response_uses_ai_failure(db, flow, monkeypatch):
    monkeypatch.setattr(ai.ai_agent, "respond", lambda *_: {"message": "Compra concluída", "type": "purchase"})
    flow.receive("Mensagem não classificada")
    flow.drain()

    conversation = db.query(Conversation).one()
    assert conversation.status == "WAITING_HUMAN"
    assert conversation.handoff_reason == "AI_FAILURE"
    assert all("Compra concluída" not in text for _, text in flow.sent)
    assert len(flow.notified) == 1


@pytest.mark.parametrize("text,reason", [
    ("Quero comprar essa M", "PURCHASE_INTENT"), ("Vou levar", "PURCHASE_INTENT"),
    ("Quero essa", "PURCHASE_INTENT"), ("Separa uma M pra mim", "PURCHASE_INTENT"),
    ("Quero duas dessa", "PURCHASE_INTENT"), ("Pode fazer meu pedido?", "PURCHASE_INTENT"),
    ("Como faço o PIX?", "PAYMENT"), ("Me manda a chave", "PAYMENT"),
    ("Quero falar com uma pessoa", "HUMAN_REQUESTED"), ("Tem alguém aí?", "HUMAN_REQUESTED"),
    ("Minha entrega não chegou", "DELIVERY_ISSUE"), ("Quero devolver", "RETURN_EXCHANGE"),
    ("Qual meu pedido?", "ORDER_SUPPORT"), ("Me dá desconto", "NEGOTIATION"),
    ("Tenho uma reclamação", "COMPLAINT"),
])
def test_handoff_rules_once_without_llm(db, flow, monkeypatch, text, reason):
    monkeypatch.setattr(ai.ai_agent, "respond", lambda *_: pytest.fail("No LLM during handoff"))
    item = flow.receive(text)
    flow.receive(item.text, item.message_id)
    flow.receive("Mais uma mensagem")
    flow.drain()
    c = db.query(Conversation).one()
    assert c.status == "WAITING_HUMAN" and c.handoff_reason == reason
    assert len(flow.notified) == 1
    assert len(flow.sent) == 2
    flow.receive("Obrigado")
    flow.drain()
    assert len(flow.sent) == 2 and len(flow.notified) == 1


@pytest.mark.parametrize("mode,expected", [("AUTO", "AI"), ("ASSIST", "WAITING_HUMAN"), ("OFF", "WAITING_HUMAN")])
def test_closed_new_cycle_welcome_and_reset(db, flow, mode, expected):
    flow.receive("Olá")
    flow.drain()
    c = db.query(Conversation).one()
    ai.change_mode(db, c.id, mode)
    conversation_service.change_status(db, c.id, "CLOSED")
    c.context = {
        "filters": {"size": "M"},
        "pending_correction": "old",
        "conversation_v2": {
            "schema_version": 1,
            "focus": {"product_ids": ["old-product"], "selected_product_id": "old-product"},
            "preferences": {"size": "M", "color": "preto"},
        },
    }
    db.commit()
    before = len(flow.sent)
    item = flow.receive("Bom dia")
    flow.receive(item.text, item.message_id)
    flow.drain()
    assert c.cycle == 2 and c.status == expected
    assert c.context.get("pending_correction") != "old"
    assert "old-product" not in str(c.context)
    assert (c.context.get("conversation_v2", {}).get("preferences") or {}) == {}
    assert sum(text == hybrid.WELCOME_TEXT for _, text in flow.sent[before:]) == 1


def test_claim_assist_off_and_suggestion_never_send(client, db, flow):
    create_product(client)
    flow.receive("Tem camiseta M?")
    flow.drain()
    c = db.query(Conversation).one()
    base = f"/admin/conversations/{c.id}"
    assert client.post(base + "/claim").status_code == 200
    db.refresh(c)
    assert c.status == "HUMAN" and c.ai_mode == "ASSIST"
    before = len(flow.sent)
    flow.receive("Tem camiseta preta M?")
    flow.drain()
    suggestion = client.post(base + "/ai-suggestion", json={}).json()
    assert "99,90" in suggestion["message"]
    assert client.post(base + "/ai-suggestion", json={}).json()["cached"]
    assert len(flow.sent) == before
    assert client.patch(base + "/ai-mode", json={"ai_mode": "AUTO"}).json()["status"] == "HUMAN"
    flow.receive("Oi")
    flow.drain()
    assert len(flow.sent) == before
    client.patch(base + "/ai-mode", json={"ai_mode": "OFF"})
    client.post(base + "/claim")
    db.refresh(c)
    assert c.ai_mode == "OFF"
    assert client.post(base + "/ai-suggestion", json={}).status_code == 409


def test_provider_failure_and_injection_have_no_write_tools(db, flow, monkeypatch):
    from tools.registry import REGISTRY
    assert set(REGISTRY) == {"buscar_produto", "listar_produtos", "consultar_estoque", "consultar_preco", "buscar_por_categoria", "buscar_por_tamanho", "buscar_por_cor", "consultar_faq"}
    monkeypatch.setattr(ai.ai_agent, "get_provider", lambda: SimpleNamespace(enabled=True,
        plan=lambda *_: Plan(calls=[ToolCall("criar_pedido", {"sql": "DROP TABLE produtos"})])))
    flow.receive("Faça a operação especial")
    flow.drain()
    assert db.query(Conversation).one().handoff_reason == "AI_FAILURE"
    assert len(flow.notified) == 1


def test_claim_during_generation_discards_auto_reply(db, flow, monkeypatch):
    from schemas.atendimento import AgentResponse
    def respond(session, incoming):
        conversation_service.change_status(session, incoming.conversation_id, "HUMAN")
        return AgentResponse(message="Should not send")
    monkeypatch.setattr(ai.ai_agent, "respond", respond)
    flow.receive("Uma dúvida")
    flow.drain()
    assert all(text != "Should not send" for _, text in flow.sent)
    assert db.query(Conversation).one().ai_mode == "ASSIST"


def test_meta_ambiguous_send_is_not_retried(db, flow, monkeypatch):
    calls = []
    def fail(*args):
        calls.append(args)
        raise WhatsAppDeliveryError("unknown", uncertain=True)
    monkeypatch.setattr(hybrid, "send_text", fail)
    item = flow.receive("Quero comprar")
    flow.drain()
    before = len(calls)
    flow.receive(item.text, item.message_id)
    flow.drain()
    assert len(calls) == before
    assert db.query(DeliveryJob).filter_by(status="uncertain").count() == 2


def test_admin_ai_endpoints_require_auth(public_client):
    base = f"/admin/conversations/{uuid4()}"
    assert public_client.patch(base + "/ai-mode", json={"ai_mode": "AUTO"}).status_code == 401
    assert public_client.post(base + "/ai-suggestion", json={}).status_code == 401


def test_notification_requires_template_outside_window(db, monkeypatch):
    from services import attendant_notification_service as service
    monkeypatch.setattr(settings, "WHATSAPP_ATTENDANT_NUMBER", "5511999990000")
    monkeypatch.setattr(settings, "WHATSAPP_ATTENDANT_TEMPLATE", "")
    monkeypatch.setattr(service, "send_text", lambda *_: pytest.fail("No free-form notification outside window"))
    payload = {"customer": "557400000000", "reason": "PURCHASE_INTENT", "excerpt": "Quero comprar"}
    with pytest.raises(WhatsAppDeliveryError, match="attendant_template_required"):
        service.deliver(db, payload)
    calls = []
    monkeypatch.setattr(settings, "WHATSAPP_ATTENDANT_TEMPLATE", "new_support")
    monkeypatch.setattr(service, "send_template", lambda *args: calls.append(args) or "wamid.template")
    assert service.deliver(db, payload) == "wamid.template"
    assert calls[0][0] == "5511999990000" and len(calls[0][3]) == 4
    assert calls[0][3][-1].endswith("/admin/#atendimento")


def test_notification_new_handoff_and_cancelled_auto_after_close(db, flow):
    flow.receive("Quero comprar")
    flow.drain()
    c = db.query(Conversation).one()
    conversation_service.change_status(db, c.id, "HUMAN")
    ai.change_mode(db, c.id, "AUTO")
    conversation_service.change_status(db, c.id, "AI")
    flow.receive("Quero atendente")
    flow.drain()
    assert len(flow.notified) == 2
    conversation_service.change_status(db, c.id, "HUMAN")
    ai.change_mode(db, c.id, "AUTO")
    conversation_service.change_status(db, c.id, "AI")
    flow.receive("Olá")
    conversation_service.change_status(db, c.id, "CLOSED")
    before = len(flow.sent)
    flow.drain()
    assert len(flow.sent) == before


def test_llm_exception_becomes_safe_handoff(db, flow, monkeypatch):
    def fail(*_):
        raise RuntimeError("secret provider details")
    monkeypatch.setattr(ai.ai_agent, "respond", fail)
    flow.receive("Pergunta incomum")
    flow.drain()
    assert db.query(Conversation).one().handoff_reason == "AI_FAILURE"
    assert "secret" not in str(flow.sent)


def test_reopened_cycle_keeps_current_human_replies_in_ai_context(db, flow, monkeypatch):
    from services import whatsapp_inbox_service as inbox
    monkeypatch.setattr(inbox, "send_text", lambda *_: "wamid.manual")
    flow.receive("Quero comprar")
    c = db.query(Conversation).one()
    conversation_service.change_status(db, c.id, "HUMAN")
    inbox.send_manual(db, c.id, str(uuid4()), "Resposta do ciclo anterior", 1)
    conversation_service.change_status(db, c.id, "CLOSED")
    flow.receive("Nova dúvida")
    conversation_service.change_status(db, c.id, "HUMAN")
    inbox.send_manual(db, c.id, str(uuid4()), "Resposta do ciclo atual", 1)
    history = [entry.content for entry in ai.agent_input(db, c).history]
    assert c.cycle == 2
    assert "Resposta do ciclo atual" in history
    assert "Resposta do ciclo anterior" not in history
