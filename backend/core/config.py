from pathlib import Path
import warnings

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: SecretStr
    SECRET_KEY: SecretStr
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, gt=0)
    LOGIN_ATTEMPTS: int = Field(default=10, gt=0)
    LOGIN_WINDOW_SECONDS: int = Field(default=60, gt=0)
    MAX_REQUEST_BODY_BYTES: int = Field(default=1_048_576, gt=0)
    MAX_LOGIN_BODY_BYTES: int = Field(default=16_384, gt=0)
    CORS_ORIGINS: list[str] = [
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://[::1]:5500",
        "https://dark-district-shop.andersongaalves1.workers.dev",
        "https://darkdistrict.com.br",
        "https://www.darkdistrict.com.br",
    ]

    @field_validator("DATABASE_URL", "SECRET_KEY")
    @classmethod
    def require_secret_value(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("A configuração obrigatória não pode estar vazia.")
        return value

    @model_validator(mode="after")
    def warn_short_signing_key(self):
        minimum = {"HS256": 32, "HS384": 48, "HS512": 64}.get(self.ALGORITHM)
        if minimum and len(self.SECRET_KEY.get_secret_value().encode("utf-8")) < minimum:
            # Existing credentials are not rotated or invalidated automatically.
            warnings.warn(
                f"SECRET_KEY abaixo do mínimo de {minimum} bytes para {self.ALGORITHM}. "
                "Configure uma chave aleatória forte no ambiente.",
                RuntimeWarning,
                stacklevel=2,
            )
        return self

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )


settings = Settings()
