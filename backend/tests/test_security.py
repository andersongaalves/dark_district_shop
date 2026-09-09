from core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from models.usuario import Usuario


def test_hash_password():
    password = "senha-segura"

    password_hash = hash_password(password)

    assert password_hash != password
    assert verify_password(password, password_hash)


def test_verify_password_incorreta():
    password_hash = hash_password("senha-segura")

    assert not verify_password(
        "senha-incorreta",
        password_hash
    )


def test_create_access_token():
    token = create_access_token({
        "sub": "admin"
    })

    assert token
    assert isinstance(token, str)


def test_get_current_user(client, db):
    password_hash = hash_password("senha-segura")

    usuario = Usuario(
        username="admin",
        password_hash=password_hash,
        active=True
    )

    db.add(usuario)
    db.commit()
    db.refresh(usuario)

    token = create_access_token({
        "sub": usuario.username
    })

    current_user = get_current_user(
        token=token,
        db=db
    )

    assert current_user.id == usuario.id
    assert current_user.username == "admin"


def test_get_current_user_usuario_inexistente(client, db):
    token = create_access_token({
        "sub": "usuario-inexistente"
    })

    try:
        get_current_user(
            token=token,
            db=db
        )
        assert False
    except Exception as error:
        assert error.status_code == 401


def test_get_current_user_usuario_desativado(client, db):
    password_hash = hash_password("senha-segura")

    usuario = Usuario(
        username="desativado",
        password_hash=password_hash,
        active=False
    )

    db.add(usuario)
    db.commit()
    db.refresh(usuario)

    token = create_access_token({
        "sub": usuario.username
    })

    try:
        get_current_user(
            token=token,
            db=db
        )
        assert False
    except Exception as error:
        assert error.status_code == 401


def test_get_current_user_token_invalido(client, db):
    try:
        get_current_user(
            token="token-invalido",
            db=db
        )
        assert False
    except Exception as error:
        assert error.status_code == 401