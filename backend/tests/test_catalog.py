import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from models.catalog import Category
from test_produtos import produto_payload


def create_category(client, **overrides):
    response = client.post("/categorias", json={"name": "Camisetas", "slug": "camisetas", **overrides})
    assert response.status_code == 201, response.text
    return response.json()


def create_collection(client):
    response = client.post("/colecoes", json={"name": "Nocturne", "slug": "nocturne", "description": "Linha noturna"})
    assert response.status_code == 201
    return response.json()


@pytest.mark.parametrize("endpoint", ["/categorias", "/colecoes"])
def test_configuration_crud(client, endpoint):
    response = client.post(endpoint, json={"name": " Peças especiais ", "slug": "pecas-especiais"})
    assert response.status_code == 201
    record = response.json()
    assert record["name"] == "Peças especiais"
    path = f"{endpoint}/{record['id']}"
    assert client.post(endpoint, json={"name": record["name"], "slug": "outro"}).status_code == 409
    edited = client.patch(path, json={"name": "Novo nome", "slug": "novo-nome", "active": False})
    assert edited.status_code == 200
    assert edited.json()["active"] is False
    assert client.get(endpoint + "?active=true").json() == []
    assert len(client.get(endpoint + "?active=false").json()) == 1
    assert client.patch(path, json={"active": True}).status_code == 200
    assert client.delete(path).status_code == 204
    assert client.patch(path, json={"name": "Outro"}).status_code == 404
    assert client.delete(path).status_code == 404


@pytest.mark.parametrize("endpoint", ["/categorias", "/colecoes"])
@pytest.mark.parametrize("method,suffix", [("post", ""), ("patch", "/1"), ("delete", "/1")])
@pytest.mark.parametrize("token", [None, "invalid"])
def test_configuration_writes_require_auth(public_client, endpoint, method, suffix, token):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = public_client.request(method, endpoint + suffix, headers=headers, json={"name": "Peça", "slug": "peca"})
    assert response.status_code == 401


@pytest.mark.parametrize("payload", [{"name": " ", "slug": "ok"}, {"name": "Peça", "slug": "../bad"},
    {"name": "Peça", "slug": "<script>"}, {"name": "x" * 101, "slug": "ok"}])
def test_configuration_validation(client, payload):
    assert client.post("/categorias", json=payload).status_code == 422


def test_product_relations_rename_deactivation_and_safe_delete(client):
    category = create_category(client)
    collection = create_collection(client)
    payload = {**produto_payload(), "category_id": category["id"], "collection_id": collection["id"],
               "product_type": "brecho", "is_offer": True}
    del payload["category"]
    created = client.post("/produtos", json=payload)
    assert created.status_code == 201, created.text
    product = created.json()
    assert product["category"] == category["name"]
    assert product["featured"] and product["is_offer"] and product["available"]
    for endpoint, record in [("categorias", category), ("colecoes", collection)]:
        path = f"/{endpoint}/{record['id']}"
        assert client.delete(path).status_code == 409
        assert client.patch(path, json={"active": False}).status_code == 200
    assert client.get("/produtos/prod-001").json()["available"] is True
    assert client.put("/produtos/prod-001", json={"title": "Alterada", "category_id": category["id"],
                                               "collection_id": collection["id"]}).status_code == 200
    assert client.post("/produtos", json={**payload, "id": "new"}).status_code == 422
    new_category = create_category(client, name="Calças", slug="calcas")
    assert client.post("/produtos", json={**payload, "id": "new", "category_id": new_category["id"]}).status_code == 422
    renamed = client.patch(f"/categorias/{category['id']}", json={"name": "Renomeada"})
    assert renamed.status_code == 200
    assert client.get("/produtos/prod-001").json()["category"] == "Renomeada"
    updated = client.put("/produtos/prod-001", json={"collection_id": None, "category_id": new_category["id"]})
    assert updated.json()["collection_id"] is None
    assert client.delete(f"/categorias/{category['id']}").status_code == 204
    assert client.delete(f"/colecoes/{collection['id']}").status_code == 204
    assert client.get("/produtos/prod-001").status_code == 200


def test_collection_description_can_be_cleared(client):
    collection = create_collection(client)
    response = client.patch(f"/colecoes/{collection['id']}", json={"description": None})
    assert response.json()["description"] is None


def test_legacy_writes_resolve_real_categories(client, db):
    first = client.post("/produtos", json=produto_payload()).json()
    second = client.post("/produtos", json={**produto_payload(), "id": "second"}).json()
    assert first["category_id"] == second["category_id"]
    assert len(db.scalars(select(Category)).all()) == 1
    assert first["product_type"] == "catalogo" and first["collection_id"] is None


def test_filters_are_independent_and_composable(client):
    category = create_category(client)
    collection = create_collection(client)
    for index, kind in enumerate(["catalogo", "brecho", "drop"]):
        payload = {**produto_payload(), "id": kind, "product_type": kind, "category_id": category["id"],
                   "collection_id": collection["id"] if index == 1 else None, "featured": index != 0,
                   "is_offer": index != 0, "available": index != 2}
        assert client.post("/produtos", json=payload).status_code == 201
        assert [p["id"] for p in client.get(f"/produtos?product_type={kind}").json()] == [kind]
    for query in ["featured=true&available=true", "is_offer=true&available=true",
                  f"collection_id={collection['id']}", f"category_id={category['id']}&product_type=brecho"]:
        assert [p["id"] for p in client.get("/produtos?" + query).json()] == ["brecho"]
    assert [p["id"] for p in client.get("/produtos?featured=false&is_offer=false").json()] == ["catalogo"]
    for query in ["product_type=offer", "category_id=0", "collection_id=-1", "available=wrong"]:
        assert client.get("/produtos?" + query).status_code == 422


@pytest.mark.parametrize("change,status", [({"category_id": 999}, 404), ({"collection_id": 999}, 404),
    ({"category_id": None}, 422), ({"product_type": "oferta"}, 422), ({"category_id": -1}, 422)])
def test_product_rejects_invalid_relations(client, change, status):
    client.post("/produtos", json=produto_payload())
    assert client.put("/produtos/prod-001", json=change).status_code == status


def test_variant_ids_survive_edits_and_foreign_ids_are_rejected(client):
    product = client.post("/produtos", json=produto_payload()).json()
    variants = product["variants"]
    variants[0]["quantity"] = 2
    assert client.put("/produtos/prod-001", json={"variants": variants}).json()["variants"] == variants
    # Old clients without IDs preserve identity through an exact size/color match.
    without_ids = [{k: v for k, v in variant.items() if k != "id"} for variant in variants]
    assert client.put("/produtos/prod-001", json={"variants": without_ids}).json()["variants"] == variants
    other = client.post("/produtos", json={**produto_payload(), "id": "other"}).json()
    assert client.put("/produtos/prod-001", json={"title": "Must roll back", "variants": other["variants"]}).status_code == 422
    assert client.get("/produtos/prod-001").json()["title"] == product["title"]
    assert client.put("/produtos/prod-001", json={"variants": [variants[0], variants[0]]}).status_code == 422
    assert client.put("/produtos/prod-001", json={"variants": [variants[1]]}).json()["variants"] == [variants[1]]


def test_database_itself_rejects_invalid_type_and_deleting_linked_category(client, db):
    product = client.post("/produtos", json=produto_payload()).json()
    with pytest.raises(IntegrityError):
        db.execute(text("UPDATE produtos SET product_type = 'oferta'"))
    db.rollback()
    with pytest.raises(IntegrityError):
        db.execute(text("DELETE FROM categorias WHERE id = :id"), {"id": product["category_id"]})
    db.rollback()
    assert client.get("/produtos/prod-001").status_code == 200


def test_product_requires_category_and_rejects_conflicting_legacy_label(client):
    category = create_category(client)
    payload = produto_payload()
    del payload["category"]
    assert client.post("/produtos", json=payload).status_code == 422
    response = client.post("/produtos", json={**payload, "category_id": category["id"], "category": "Outra"})
    assert response.status_code == 422


def test_failed_category_rename_rolls_back_product_labels(client):
    category = create_category(client)
    create_category(client, name="Calças", slug="calcas")
    client.post("/produtos", json=produto_payload())
    assert client.patch(f"/categorias/{category['id']}", json={"name": "Calças"}).status_code == 409
    assert client.get("/produtos/prod-001").json()["category"] == "Camisetas"
