def produto_payload():
    return {
        "id": "prod-001",
        "title": "Camiseta Dark District",
        "description": "Camiseta preta",
        "price": 99.90,
        "category": "Camisetas",
        "gender": "Unissex",
        "available": True,
        "featured": True,
        "images": [
            {
                "url": "https://exemplo.com/imagem1.jpg",
                "ordem": 0
            },
            {
                "url": "https://exemplo.com/imagem2.jpg",
                "ordem": 1
            }
        ],
        "variants": [
            {
                "size": "M",
                "color": "Preto",
                "quantity": 5
            },
            {
                "size": "G",
                "color": "Preto",
                "quantity": 3
            }
        ]
    }


def test_listar_produtos_vazio(client):
    response = client.get("/produtos")

    assert response.status_code == 200
    assert response.json() == []


def test_criar_produto(client):
    response = client.post(
        "/produtos",
        json=produto_payload()
    )

    assert response.status_code == 201

    data = response.json()

    assert data["id"] == "prod-001"
    assert data["title"] == "Camiseta Dark District"
    assert data["price"] == 99.90
    assert data["featured"] is True
    assert len(data["images"]) == 2
    assert len(data["variants"]) == 2


def test_obter_produto(client):
    client.post(
        "/produtos",
        json=produto_payload()
    )

    response = client.get(
        "/produtos/prod-001"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == "prod-001"
    assert len(data["images"]) == 2
    assert len(data["variants"]) == 2


def test_produto_inexistente(client):
    response = client.get(
        "/produtos/produto-inexistente"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Produto não encontrado."
    )


def test_id_duplicado(client):
    payload = produto_payload()

    primeira = client.post(
        "/produtos",
        json=payload
    )

    segunda = client.post(
        "/produtos",
        json=payload
    )

    assert primeira.status_code == 201
    assert segunda.status_code == 409


def test_atualizar_produto(client):
    client.post(
        "/produtos",
        json=produto_payload()
    )

    response = client.put(
        "/produtos/prod-001",
        json={
            "title": "Camiseta Atualizada",
            "price": 129.90,
            "images": [
                {
                    "url": "https://exemplo.com/nova.jpg",
                    "ordem": 0
                }
            ],
            "variants": [
                {
                    "size": "GG",
                    "color": "Vermelho",
                    "quantity": 10
                }
            ]
        }
    )

    assert response.status_code == 200

    data = response.json()

    assert data["title"] == "Camiseta Atualizada"
    assert data["price"] == 129.90
    assert len(data["images"]) == 1
    assert data["images"][0]["url"] == (
        "https://exemplo.com/nova.jpg"
    )
    assert len(data["variants"]) == 1
    assert data["variants"][0]["size"] == "GG"


def test_marcar_produto_vendido(client):
    client.post(
        "/produtos",
        json=produto_payload()
    )

    response = client.patch(
        "/produtos/prod-001/vendido"
    )

    assert response.status_code == 200
    assert response.json()["available"] is False


def test_excluir_produto(client):
    client.post(
        "/produtos",
        json=produto_payload()
    )

    response = client.delete(
        "/produtos/prod-001"
    )

    assert response.status_code == 204

    response = client.get(
        "/produtos/prod-001"
    )

    assert response.status_code == 404