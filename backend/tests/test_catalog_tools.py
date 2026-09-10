from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event

from models.produto import Produto
from services.produtos import listar_produtos
from test_produtos import produto_payload
from tools.registry import REGISTRY, definitions, execute


def create_product(client, **changes):
    response = client.post("/produtos", json={**produto_payload(), **changes})
    assert response.status_code == 201, response.text
    return response.json()


def test_tools_have_exact_allowlist_and_strict_arguments(db):
    assert set(REGISTRY) == {"buscar_produto", "listar_produtos", "consultar_estoque", "consultar_preco",
                             "buscar_por_categoria", "buscar_por_tamanho", "buscar_por_cor", "consultar_faq"}
    for definition in definitions():
        schema = definition["function"]["parameters"]
        assert definition["function"]["strict"] is True
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])
    assert execute(db, "delete_customers", {}).error
    assert execute(db, "listar_produtos", {"sql": "DROP TABLE produtos"}).error


@pytest.mark.parametrize("arguments", [{"limit": 100}, {"limit": "5"}, {"max_price": -1},
                                         {"max_price": float("inf")}, {"size": ""},
                                         {"product_type": "anything"}, {"query": "x" * 101}])
def test_tool_parameters_are_bounded(db, arguments):
    assert execute(db, "buscar_produto", arguments).error


def test_size_and_color_must_match_one_stocked_variant(client, db):
    create_product(client, variants=[{"size": "M", "color": "Branco", "quantity": 2},
                                     {"size": "P", "color": "Preto", "quantity": 3},
                                     {"size": "M", "color": "Preto", "quantity": 0}])
    assert execute(db, "buscar_produto", {"size": "M", "color": "preto"}).products == []
    result = execute(db, "buscar_por_cor", {"size": "p", "color": "preto"})
    assert [product.id for product in result.products] == ["prod-001"]


def test_available_flag_does_not_invent_stock_or_variant_information(client, db):
    create_product(client, variants=[{"size": "M", "color": "Preto", "quantity": 0}])
    assert execute(db, "listar_produtos", {}).products == []
    stock = execute(db, "consultar_estoque", {"product_id": "prod-001"})
    assert stock.products[0].variants[0].quantity == 0
    create_product(client, id="unknown-stock", variants=[])
    products = execute(db, "listar_produtos", {}).products
    assert [product.id for product in products] == ["unknown-stock"]
    assert products[0].variants == []
    assert execute(db, "buscar_por_tamanho", {"size": "M"}).products == []


def test_price_filter_uses_current_offer_and_reverts_after_expiry(client, db):
    create_product(client, price=100, is_offer=True, offer_price=60,
                   offer_ends_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat())
    result = execute(db, "listar_produtos", {"max_price": 80})
    assert result.products[0].effective_price == 60
    product = db.get(Produto, "prod-001")
    product.offer_ends_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    assert execute(db, "listar_produtos", {"max_price": 80}).products == []
    assert execute(db, "consultar_preco", {"product_id": "prod-001"}).products[0].effective_price == 100


def test_substrings_are_literal_and_query_is_limited_in_database(client, db):
    create_product(client)
    create_product(client, id="prod-002")
    statements = []
    def capture(_connection, _cursor, statement, parameters, _context, _many):
        statements.append((statement, parameters))
    event.listen(db.bind, "before_cursor_execute", capture)
    try:
        assert len(execute(db, "listar_produtos", {"limit": 1}).products) == 1
        assert execute(db, "buscar_produto", {"query": "%"}).products == []
        assert execute(db, "buscar_produto", {"query": "' OR 1=1 --"}).products == []
    finally:
        event.remove(db.bind, "before_cursor_execute", capture)
    assert any("LIMIT" in statement for statement, _ in statements)
    assert all("' OR 1=1 --" not in statement for statement, _ in statements)
    assert len(listar_produtos(db)) == 2  # Existing public listing retains its behavior.


def test_category_size_and_color_use_existing_catalog_and_safe_product_link(client, db):
    create_product(client, id="a?x&y")
    for name, arguments in (("buscar_por_categoria", {"category": "camisetas"}),
                             ("buscar_por_tamanho", {"size": "M"}),
                             ("buscar_por_cor", {"color": "PRETO"})):
        product = execute(db, name, arguments).products[0]
        assert product.id == "a?x&y"
        assert product.url == "https://darkdistrict.com.br/pages/produto/index.html?id=a%3Fx%26y"
    assert execute(db, "consultar_preco", {"product_id": "missing"}).products == []
