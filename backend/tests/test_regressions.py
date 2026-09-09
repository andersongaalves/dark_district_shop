from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt
from sqlalchemy import event, select

from core.config import settings
from core.security import create_access_token
from models.produto import ProdutoImagem, ProdutoVariante
from test_auth import criar_usuario
from test_produtos import produto_payload


@pytest.mark.parametrize("method,path", [
    ("post", "/produtos"), ("put", "/produtos/item"),
    ("patch", "/produtos/item/vendido"), ("delete", "/produtos/item"),
])
@pytest.mark.parametrize("token", [None, "invalid"])
def test_mutations_require_real_authentication(public_client, method, path, token):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = public_client.request(method, path, headers=headers, json=produto_payload())
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("kind", ["expired", "inactive", "missing_user", "missing_sub"])
def test_invalid_sessions_cannot_write(public_client, db, kind):
    if kind != "missing_user":
        criar_usuario(db, active=kind != "inactive")
    payload = {"sub": "admin"}
    if kind == "missing_sub":
        payload = {}
    if kind == "expired":
        payload["exp"] = datetime.now(timezone.utc) - timedelta(seconds=1)
        token = jwt.encode(payload, settings.SECRET_KEY.get_secret_value(), algorithm=settings.ALGORITHM)
    else:
        token = create_access_token(payload)
    response = public_client.post("/produtos", json=produto_payload(),
                                  headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_real_authenticated_crud(public_client, db):
    criar_usuario(db)
    login = public_client.post("/auth/login", data={"username": "admin", "password": "123456"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert public_client.post("/produtos", json=produto_payload(), headers=headers).status_code == 201
    assert public_client.get("/produtos/prod-001").status_code == 200
    updated = public_client.put("/produtos/prod-001", json={"title": "Atualizado"}, headers=headers)
    assert updated.json()["title"] == "Atualizado"
    assert public_client.patch("/produtos/prod-001/vendido", headers=headers).json()["available"] is False
    deleted = public_client.delete("/produtos/prod-001", headers=headers)
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert public_client.get("/produtos/prod-001").status_code == 404


def test_partial_update_preserves_relations_and_false_values(client):
    original = client.post("/produtos", json=produto_payload()).json()
    updated = client.put("/produtos/prod-001", json={
        "price": 0, "featured": False, "available": False, "title": None,
    }).json()
    assert updated["price"] == 0
    assert updated["featured"] is False
    assert updated["available"] is False
    assert updated["title"] == original["title"]
    assert updated["images"] == original["images"]
    assert updated["variants"] == original["variants"]


def test_empty_relations_delete_orphans(client, db):
    client.post("/produtos", json=produto_payload())
    updated = client.put("/produtos/prod-001", json={"images": [], "variants": []})
    assert updated.status_code == 200
    assert updated.json()["images"] == updated.json()["variants"] == []
    assert db.scalars(select(ProdutoImagem)).all() == []
    assert db.scalars(select(ProdutoVariante)).all() == []


def test_images_follow_explicit_order(client):
    payload = produto_payload()
    payload["images"].reverse()
    result = client.post("/produtos", json=payload).json()
    assert [image["ordem"] for image in result["images"]] == [0, 1]


@pytest.mark.parametrize("method,path", [
    ("put", "/produtos/missing"), ("patch", "/produtos/missing/vendido"),
    ("delete", "/produtos/missing"),
])
def test_missing_mutation_product(client, method, path):
    response = client.request(method, path, json={})
    assert response.status_code == 404
    assert response.json()["detail"] == "Produto não encontrado."


def test_product_listing_has_bounded_queries(client, db):
    for number in range(4):
        payload = produto_payload()
        payload["id"] = f"product-{number}"
        client.post("/produtos", json=payload)
    queries = []
    def record_query(_connection, _cursor, statement, *_args):
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)
    event.listen(db.bind, "before_cursor_execute", record_query)
    try:
        response = client.get("/produtos")
    finally:
        event.remove(db.bind, "before_cursor_execute", record_query)
    assert response.status_code == 200
    assert len(response.json()) == 4
    assert len(queries) == 3
