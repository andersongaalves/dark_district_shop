from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from core.security import (
    DUMMY_HASH,
    create_access_token,
    verify_password,
)
from database import get_db
from models.usuario import Usuario
from schemas.auth import TokenResponse


router = APIRouter(
    prefix="/auth",
    tags=["Autenticação"]
)


@router.post(
    "/login",
    response_model=TokenResponse
)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    usuario = (
        db.query(Usuario)
        .filter(Usuario.username == form_data.username)
        .first()
    )

    valid_password = verify_password(
        form_data.password,
        usuario.password_hash if usuario else DUMMY_HASH,
    )
    if not usuario or not valid_password or not usuario.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha inválidos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token({
        "sub": usuario.username
    })

    return {
        "access_token": token,
        "token_type": "bearer"
    }
