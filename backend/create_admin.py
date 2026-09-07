import os

from database import SessionLocal
from models.usuario import Usuario
from core.security import hash_password


USERNAME = os.getenv("ADMIN_USERNAME")
PASSWORD = os.getenv("ADMIN_PASSWORD")


def criar_admin():
    if not USERNAME or not PASSWORD:
        raise RuntimeError(
            "ADMIN_USERNAME e ADMIN_PASSWORD devem estar definidos."
        )

    db = SessionLocal()

    try:
        usuario = (
            db.query(Usuario)
            .filter(Usuario.username == USERNAME)
            .first()
        )

        if usuario:
            print("Usuário administrador já existe.")
            return

        usuario = Usuario(
            username=USERNAME,
            password_hash=hash_password(PASSWORD),
            active=True,
        )

        db.add(usuario)
        db.commit()

        print("Usuário administrador criado com sucesso.")

    finally:
        db.close()


if __name__ == "__main__":
    criar_admin()