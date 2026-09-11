from types import SimpleNamespace
from uuid import uuid4

import pytest

from core.config import settings
from integrations.llm.provider import Plan, ToolCall
from schemas.atendimento import AgentInput
from services import ai_agent
from services.faq import list_faq
from test_catalog_tools import create_product
from test_webchat import headers, session
from tools.registry import execute


def incoming(message, channel="web", **changes):
    return AgentInput(channel=channel, conversation_id="faq-conversation", customer_id="faq-customer",
                      message=message, **changes)


def test_public_faq_contains_approved_policies_without_auth_or_chat(public_client, monkeypatch):
    monkeypatch.setattr(settings, "CHAT_ENABLED", False)
    response = public_client.get("/faq")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert response.json() == [item.model_dump() for item in list_faq()]
    answers = {item["id"]: item["answer"] for item in response.json()}
    assert set(answers) == {"compra", "entrega", "devolucao", "atendimento"}
    assert "Continuar pelo WhatsApp" in answers["compra"]
    assert "não reserva estoque" in answers["compra"]
    assert "entregador vai até o endereço definido" in answers["entrega"]
    assert "até 7 dias após o recebimento" in answers["devolucao"]
    assert answers["atendimento"] == "Atendemos Juazeiro e região."


@pytest.mark.parametrize("channel", ["web", "whatsapp"])
@pytest.mark.parametrize("message,topic", [
    ("Como funciona a compra?", "compra"),
    ("Como compro pelo site?", "compra"),
    ("Como é entregue?", "entrega"),
    ("Vocês entregam em casa?", "entrega"),
    ("Qual é o prazo para devolução?", "devolucao"),
    ("Em quantos dias posso devolver?", "devolucao"),
    ("Como solicitar devolução?", "devolucao"),
    ("Onde vocês atendem?", "atendimento"),
    ("Quais cidades vocês atendem?", "atendimento"),
])
def test_known_faq_answers_are_shared_without_provider_or_database(monkeypatch, channel, message, topic):
    monkeypatch.setattr(ai_agent, "get_provider", lambda: pytest.fail("FAQ must not need an LLM"))
    # No Session at all: these are public facts, independent of the catalog DB.
    response = ai_agent.respond(None, incoming(message, channel))
    assert response.message == list_faq(topic)[0].answer
    assert not response.handoff and response.type == "message"
    assert response.products == []


@pytest.mark.parametrize("message", [
    "Quero devolver minha peça", "Preciso de uma devolução", "Quero solicitar a devolução",
    "Gostaria de fazer uma devolução", "Quero atendente para saber como comprar", "Preciso de estorno",
])
def test_return_requests_and_human_requests_still_take_priority(message, monkeypatch):
    monkeypatch.setattr(ai_agent, "get_provider", lambda: pytest.fail("handoff must be local"))
    assert ai_agent.respond(None, incoming(message)).handoff


@pytest.mark.parametrize("message", [
    "Qual o prazo de entrega?",
    "Posso devolver uma roupa usada?", "A devolução tem taxa?",
])
def test_unregistered_policy_details_are_referred_to_staff(message):
    response = ai_agent.respond(None, incoming(message))
    assert not response.handoff
    assert response.actions[0].type == "human_handoff"
    assert "confirmada com a equipe" in response.message
    assert all(item.answer not in response.message for item in list_faq())


def test_region_answer_does_not_confirm_other_cities():
    response = ai_agent.respond(None, incoming("Vocês entregam em Salvador?"))
    assert response.message == "Atendemos Juazeiro e região."


def test_faq_tool_only_reads_published_topics():
    assert execute(None, "consultar_faq", {"topic": None}).faqs == list_faq()
    assert execute(None, "consultar_faq", {"topic": "entrega"}).faqs == list_faq("entrega")
    assert execute(None, "consultar_faq", {"topic": "entrega", "answer": "grátis"}).error
    assert execute(None, "consultar_faq", {"topic": "../../.env"}).error


def test_llm_can_choose_faq_tool_for_a_paraphrase_and_preserve_search_context(monkeypatch):
    context = {"filters": {"size": "M"}, "product_ids": ["prod-001"]}
    def plan(messages, tools):
        assert "consultar_faq" in {tool["function"]["name"] for tool in tools}
        return Plan([ToolCall("consultar_faq", {"topic": "atendimento"})])
    monkeypatch.setattr(ai_agent, "get_provider", lambda: SimpleNamespace(enabled=True, plan=plan))
    response = ai_agent.respond(None, incoming("Qual é a cobertura da DD?", context=context))
    assert response.message == list_faq("atendimento")[0].answer
    assert response.context == context


def test_faq_between_product_questions_preserves_filters(client, db):
    create_product(client)
    products = ai_agent.respond(db, incoming("Tem camiseta M?"))
    faq = ai_agent.respond(db, incoming("Como é feita a entrega?", context=products.context))
    assert faq.context == products.context
    followup = ai_agent.respond(db, incoming("E preta?", context=faq.context))
    assert followup.type == "product_results"
    assert "M / Preto: 5 un." in followup.message


def test_llm_can_combine_faq_and_catalog_facts(client, db, monkeypatch):
    create_product(client)
    monkeypatch.setattr(ai_agent, "get_provider", lambda: SimpleNamespace(enabled=True, plan=lambda *_: Plan([
        ToolCall("consultar_faq", {"topic": "atendimento"}),
        ToolCall("buscar_produto", {"query": "camiseta"}),
    ])))
    response = ai_agent.respond(db, incoming("Quero uma camiseta e saber a cobertura da DD"))
    assert response.type == "product_results"
    assert list_faq("atendimento")[0].answer in response.message
    assert "R$ 99,90" in response.message


def test_web_chat_reuses_public_faq_and_respects_handoff(public_client):
    visitor = session(public_client)
    for item in public_client.get("/faq").json():
        response = public_client.post("/api/chat/messages", headers=headers(visitor),
            json={"message_id": str(uuid4()), "message": item["question"]})
        assert response.status_code == 200
        assert response.json()["message"] == item["answer"]
        assert response.json()["status"] == "AI"
    history = public_client.get("/api/chat/messages", headers=headers(visitor)).json()
    assert len(history["messages"]) == 8
    handoff = public_client.post("/api/chat/messages", headers=headers(visitor),
        json={"message_id": str(uuid4()), "message": "Quero devolver minha peça"})
    assert handoff.json()["handoff"] is True
    paused = public_client.post("/api/chat/messages", headers=headers(visitor),
        json={"message_id": str(uuid4()), "message": "Onde vocês atendem?"})
    assert paused.json()["type"] == "silent"
