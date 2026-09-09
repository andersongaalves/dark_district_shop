from core.security import hash_password
from models.usuario import Usuario


def criar_usuario(db, username="admin", password="123456", active=True):
    usuario = Usuario(
        username=username,
        password_hash=hash_password(password),
        active=active
    )

    db.add(usuario)
    db.commit()
    db.refresh(usuario)

    return usuario


def test_login_sucesso(public_client, db):
    criar_usuario(db)

    response = public_client.post(
        "/auth/login",
        data={
            "username": "admin",
            "password": "123456"
        }
    )

    assert response.status_code == 200

    data = response.json()

    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_senha_incorreta(public_client, db):
    criar_usuario(db)

    response = public_client.post(
        "/auth/login",
        data={
            "username": "admin",
            "password": "senha_errada"
        }
    )

    assert response.status_code == 401
    assert response.json()["detail"] == (
        "Usuário ou senha inválidos."
    )


def test_login_usuario_inexistente(public_client):
    response = public_client.post(
        "/auth/login",
        data={
            "username": "nao_existe",
            "password": "123456"
        }
    )

    assert response.status_code == 401
    assert response.json()["detail"] == (
        "Usuário ou senha inválidos."
    )


def test_login_usuario_desativado(public_client, db):
    criar_usuario(
        db,
        active=False
    )

    response = public_client.post(
        "/auth/login",
        data={
            "username": "admin",
            "password": "123456"
        }
    )

    assert response.status_code == 401
    assert response.json()["detail"] == (
        "Usuário desativado."
    )


def test_token_acessa_rota_protegida(public_client, db):
    criar_usuario(db)

    login = public_client.post(
        "/auth/login",
        data={
            "username": "admin",
            "password": "123456"
        }
    )

    token = login.json()["access_token"]

    response = public_client.post(
        "/produtos",
        json={
            "id": "auth-test-001",
            "title": "Produto Teste",
            "description": "Produto para teste",
            "price": 100,
            "category": "Teste",
            "gender": "Unissex"
        },
        headers={
            "Authorization": f"Bearer {token}"
        }
    )

    assert response.status_code == 201