from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from integrations.llm.provider import Plan, ToolCall
from schemas.atendimento import ChatAction
from services import ai_agent
from services.agent_language import spelling_suggestion
from services.faq import list_faq
from test_ai_agent import incoming
from test_catalog_tools import create_product
from test_webchat import headers, session


@pytest.mark.parametrize("message,expected", [
    ("Oi, tudo bem?", "estou por aqui"), ("obg", "Por nada"), ("vlw", "Por nada"),
    ("Tchau!", "Até mais"), ("O que vc faz?", "Posso buscar"),
    ("Como escolher meu tamanho?", "compare suas medidas"),
    ("Me dá uma dica de look", "Uma ideia"),
])
def test_more_conversation_intents_do_not_need_provider_or_catalog(monkeypatch, message, expected):
    monkeypatch.setattr(ai_agent, "get_provider", lambda: pytest.fail("No provider for this intent"))
    response = ai_agent.respond(None, incoming(message))
    assert expected in response.message
    assert response.products == [] and not response.handoff


@pytest.mark.parametrize("message,expected", [
    ("Tem camissta M até R$100?", "Tem camiseta M até R$100?"),
    ("Tem croped?", "Tem cropped?"), ("Como é a entega?", "Como é a entrega?"),
    ("Quero a camissta CR-000-001 tamanho M por R$89,90", "Quero a camiseta CR-000-001 tamanho M por R$89,90"),
])
def test_typo_suggestions_preserve_identifiers_size_and_price(message, expected):
    assert spelling_suggestion(message) == expected


@pytest.mark.parametrize("message", [
    "Vocês ficam perto?", "Camisa M", "Tem camiseta?", "Camisa CR-000-001",
    "https://example.com/camissta", "camissta@example.com", "camissta-001", "x" * 501,
])
def test_correct_words_links_and_identifiers_are_not_changed(message):
    assert spelling_suggestion(message) is None


@pytest.mark.parametrize("channel", ["web", "whatsapp"])
def test_confirm_typo_searches_current_stock_in_both_channels(client, db, channel):
    create_product(client)
    request = incoming("Tem camissta preta M até R$100?")
    request.channel = channel
    suggestion = ai_agent.respond(db, request)
    assert suggestion.products == [] and "Você quis dizer" in suggestion.message
    assert [action.message for action in suggestion.actions] == ["Sim", "Não"]
    confirmed = ai_agent.respond(db, request.model_copy(update={"message": "Sim", "context": suggestion.context}))
    assert confirmed.type == "product_results"
    assert "M / Preto: 5 un." in confirmed.message and "R$ 99,90" in confirmed.message
    assert not confirmed.context.get("pending_correction")


def test_rejected_suggestion_does_not_search_and_keeps_filters(monkeypatch):
    monkeypatch.setattr(ai_agent, "get_provider", lambda: pytest.fail("No provider needed"))
    context = {"filters": {"size": "G", "max_price": 80}, "product_ids": []}
    suggestion = ai_agent.respond(None, incoming("Tem croped?", context=context))
    rejected = ai_agent.respond(None, incoming("Não", context=suggestion.context))
    assert "Escreva novamente" in rejected.message
    assert rejected.context["filters"] == context["filters"]
    assert rejected.context["pending_correction"] is None
    next_question = ai_agent.respond(None, incoming("Como comprar?", context=suggestion.context))
    assert list_faq("compra")[0].answer == next_question.message
    assert not next_question.context.get("pending_correction")


def test_confirmed_correction_reaches_provider_with_preserved_product_id(monkeypatch):
    def plan(messages, _tools):
        assert "CR-000-001" in messages[-1]["content"]
        assert "camiseta" in messages[-1]["content"]
        return Plan([ToolCall("consultar_faq", {"topic": "compra"})])
    monkeypatch.setattr(ai_agent, "get_provider", lambda: SimpleNamespace(enabled=True, plan=plan))
    suggestion = ai_agent.respond(None, incoming("Quero camissta CR-000-001"))
    response = ai_agent.respond(None, incoming("Sim", context=suggestion.context))
    assert response.message == list_faq("compra")[0].answer


def test_human_request_wins_over_a_typo_and_clears_pending(monkeypatch):
    monkeypatch.setattr(ai_agent, "get_provider", lambda: pytest.fail("No provider needed"))
    result = ai_agent.respond(None, incoming("Quero atendente para ver camissta", context={"pending_correction": "Tem cropped?"}))
    assert result.handoff and not result.context.get("pending_correction")


def test_unknown_question_never_repeats_old_catalog_query(db):
    response = ai_agent.respond(db, incoming("Explique a lua", context={
        "filters": {"query": "camiseta", "offer_active": True, "product_type": "brecho"}, "product_ids": ["prod-001"]}))
    assert not db.in_transaction()
    assert response.products == [] and "Não entendi bem" in response.message


def test_multiple_faq_questions_and_product_search_are_answered_together(client, db):
    create_product(client)
    faq = ai_agent.respond(db, incoming("Como é feita a entrega? Qual o prazo para devolução?"))
    assert list_faq("entrega")[0].answer in faq.message
    assert list_faq("devolucao")[0].answer in faq.message
    mixed = ai_agent.respond(db, incoming("Tem camiseta M? Como funciona a compra?"))
    assert mixed.type == "product_results"
    assert list_faq("compra")[0].answer in mixed.message
    assert "M / Preto: 5 un." in mixed.message


def test_unregistered_question_keeps_conversation_available(public_client):
    visitor = session(public_client)
    response = public_client.post("/api/chat/messages", headers=headers(visitor),
        json={"message_id": str(uuid4()), "message": "Qual o frete?"})
    assert response.json()["status"] == "AI" and not response.json()["handoff"]
    assert response.json()["actions"][0]["type"] == "human_handoff"
    reply = public_client.post("/api/chat/messages", headers=headers(visitor),
        json={"message_id": str(uuid4()), "message": "Como comprar?"})
    assert reply.json()["message"] == list_faq("compra")[0].answer


def test_persisted_suggestion_confirmation_and_reset_are_isolated(client):
    create_product(client)
    first, second = session(client), session(client)
    def send(visitor, message):
        response = client.post("/api/chat/messages", headers=headers(visitor), json={"message_id": str(uuid4()), "message": message})
        assert response.status_code == 200, response.text
        return response.json()
    assert "Você quis dizer" in send(first, "Tem camissta M?")["message"]
    assert send(second, "Sim")["products"] == []
    assert send(first, "Sim")["type"] == "product_results"
    assert send(first, "Começar de novo")["products"] == []
    assert send(first, "Quanto custa?")["products"] == []
    assert "Você quis dizer" in send(first, "Tem croped?")["message"]
    assert "Escreva novamente" in send(first, "Não")["message"]
    assert send(first, "Sim")["products"] == []
    history = client.get("/api/chat/messages", headers=headers(first)).json()
    assert history["messages"][0]["content"] == "Tem camissta M?"


def test_product_details_and_refinements_use_registered_data(client, db):
    create_product(client, description="<p>Algodão. Largura: 50 cm.</p>")
    first = ai_agent.respond(db, incoming("Tem camiseta M?"))
    details = ai_agent.respond(db, incoming("Qual o tecido dessa?", context=first.context))
    assert "Descrição cadastrada: Algodão. Largura: 50 cm." in details.message
    colors = ai_agent.respond(db, incoming("Quais cores tem?", context=first.context))
    assert "Preto" in colors.message
    price = ai_agent.respond(db, incoming("Quanto custa?", context=first.context))
    assert "R$ 99,90" in price.message
    relaxed = ai_agent.respond(db, incoming("Mostre outras cores", context={"filters": {"query": "camiseta", "color": "azul", "size": "M"}, "product_ids": []}))
    assert relaxed.products and relaxed.context["filters"]["size"] == "M"
    assert "color" not in relaxed.context["filters"]


def test_empty_description_does_not_invent_material(client, db):
    create_product(client, description="")
    first = ai_agent.respond(db, incoming("Tem camiseta?"))
    response = ai_agent.respond(db, incoming("Qual o material?", context=first.context))
    assert "Não há descrição cadastrada" in response.message


def test_mixed_faq_and_unknown_payment_question_does_not_invent_policy():
    response = ai_agent.respond(None, incoming("Como comprar? Vocês parcelam?"))
    assert list_faq("compra")[0].answer in response.message
    assert "confirmados com a equipe" in response.message


@pytest.mark.parametrize("message", [None, "", " ", "a\x00b", "x" * 201])
def test_suggestion_actions_require_bounded_valid_text(message):
    with pytest.raises(ValidationError):
        ChatAction(type="suggestion", label="Continuar", message=message)
