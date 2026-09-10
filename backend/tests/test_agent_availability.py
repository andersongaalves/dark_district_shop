import pytest

from services import ai_agent
from test_ai_agent import incoming
from test_catalog_tools import create_product
from tools.registry import execute


@pytest.mark.parametrize("channel", ["web", "whatsapp"])
@pytest.mark.parametrize("question,title,category,word", [
    ("Tem calça?", "Calça Cargo", "Calças", "calças"),
    ("Tem calca?", "Cargo Preta", "Calcas", "calças"),
    ("Tem saia?", "Saia Plissada", "Saias", "saias"),
])
def test_availability_answers_before_cards_and_ignores_unrelated_descriptions(client, db, monkeypatch, channel, question, title, category, word):
    create_product(client, id="wanted", title=title, category=category, description="Peça disponível.")
    # Enough recent false matches to hide the real piece if filtering were
    # performed only after the database LIMIT.
    for index in range(6):
        create_product(client, id=f"shirt-{index}", description="Combina com saia e calça.")
    monkeypatch.setattr(ai_agent, "get_provider", lambda: pytest.fail("Explicit availability uses a constrained lookup"))
    request = incoming(question)
    request.channel = channel
    response = ai_agent.respond(db, request)
    assert response.message.startswith(f"Sim, encontrei {word} disponíveis")
    assert response.message.index("Sim, encontrei") < response.message.index(title)
    assert [product.id for product in response.products] == ["wanted"]


def test_missing_garment_is_answered_without_showing_other_clothes(client, db):
    create_product(client, description="Combina com saia e calça.")
    create_product(client, id="shoes", title="Calçado Preto", category="Calçados", description="")
    response = ai_agent.respond(db, incoming("Tem calça?"))
    assert response.message.startswith("Não encontrei calças disponíveis")
    assert response.products == []
    alternative = next(action for action in response.actions if action.label == "Ver outras peças")
    next_response = ai_agent.respond(db, incoming(alternative.message, context=response.context))
    assert next_response.products
    assert "garment" not in next_response.context["filters"]


def test_new_garment_replaces_previous_product_even_with_demonstrative(client, db):
    create_product(client)
    create_product(client, id="skirt", title="Saia Preta", category="Saias")
    shirt = ai_agent.respond(db, incoming("Tem camiseta?"))
    skirt = ai_agent.respond(db, incoming("Tem essa saia?", context=shirt.context))
    assert skirt.message.startswith("Sim, encontrei saias disponíveis")
    assert [product.id for product in skirt.products] == ["skirt"]
    trousers = ai_agent.respond(db, incoming("Tem calça?", context=skirt.context))
    assert trousers.message.startswith("Não encontrei calças disponíveis")
    assert trousers.products == []


def test_no_match_explains_size_and_color_without_claiming_all_skirts_are_sold(client, db):
    create_product(client, id="skirt", title="Saia Preta", category="Saias")
    response = ai_agent.respond(db, incoming("Tem saia azul P?"))
    assert response.products == []
    assert "tamanho P" in response.message and "cor azul" in response.message
    repeated = ai_agent.respond(db, incoming("Tem saia?", context=response.context))
    assert repeated.products == [] and "cor azul" in repeated.message


@pytest.mark.parametrize("changes", [{"available": False}, {"variants": [{"size": "M", "color": "Preto", "quantity": 0}]}])
def test_sold_garment_is_not_announced_as_available(client, db, changes):
    create_product(client, id="skirt", title="Saia Preta", category="Saias", **changes)
    response = ai_agent.respond(db, incoming("Tem saia?"))
    assert response.products == []
    assert response.message.startswith("Não encontrei saias disponíveis")


def test_explicit_id_does_not_override_the_requested_garment(client, db):
    create_product(client)
    response = ai_agent.respond(db, incoming("Tem calça prod-001?"))
    assert response.products == []
    assert response.message.startswith("Não encontrei calças disponíveis")


def test_garment_filter_rejects_unknown_values(db):
    assert execute(db, "buscar_produto", {"garment": "saia' OR 1=1"}).error
