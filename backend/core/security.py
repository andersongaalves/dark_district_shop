from datetime import datetime, timedelta, timezone
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from core.config import settings
from database import get_db
from models.usuario import Usuario


pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)
MAX_PASSWORD_BYTES = 72
MAX_TOKEN_LENGTH = 4096
DUMMY_HASH = pwd_context.hash(secrets.token_urlsafe(32))

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login"
)


def hash_password(password: str) -> str:
    if not _valid_password_input(password):
        raise ValueError("A senha deve ter entre 1 e 72 bytes UTF-8 e não pode conter byte nulo.")
    return pwd_context.hash(password)


def _valid_password_input(password: str) -> bool:
    if not isinstance(password, str) or not 0 < len(password) <= MAX_PASSWORD_BYTES:
        return False
    if "\x00" in password:
        return False
    try:
        return len(password.encode("utf-8")) <= MAX_PASSWORD_BYTES
    except UnicodeEncodeError:
        return False


def verify_password(
    password: str,
    password_hash: str
) -> bool:
    if not _valid_password_input(password):
        pwd_context.verify("invalid-input", DUMMY_HASH)
        return False
    try:
        return pwd_context.verify(password, password_hash)
    except (ValueError, TypeError):
        # A malformed stored hash must deny authentication, without leaking an error.
        pwd_context.verify(password, DUMMY_HASH)
        return False


def create_access_token(data: dict) -> str:
    payload = data.copy()

    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload.update({
        "exp": expire
    })

    return jwt.encode(
        payload,
        settings.SECRET_KEY.get_secret_value(),
        algorithm=settings.ALGORITHM
    )


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Usuario:

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido ou expirado.",
        headers={
            "WWW-Authenticate": "Bearer"
        }
    )

    if not isinstance(token, str) or len(token) > MAX_TOKEN_LENGTH:
        raise credentials_exception

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY.get_secret_value(),
            algorithms=[settings.ALGORITHM],
            options={"require_exp": True, "require_sub": True},
        )

        username = payload.get("sub")

        if not isinstance(username, str) or not 0 < len(username) <= 100:
            raise credentials_exception

        if type(payload.get("exp")) is not int:
            raise credentials_exception

    except (JWTError, ValueError, TypeError, OverflowError):
        raise credentials_exception from None

    usuario = (
        db.query(Usuario)
        .filter(Usuario.username == username)
        .first()
    )

    if not usuario or not usuario.active:
        raise credentials_exception

    return usuario
