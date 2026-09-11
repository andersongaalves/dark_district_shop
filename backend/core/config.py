from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
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
    CHAT_ENABLED: bool = True
    CHAT_SESSION_HOURS: int = Field(default=24, ge=1, le=168)
    CHAT_MAX_MESSAGE_LENGTH: int = Field(default=2000, ge=1, le=2000)
    CHAT_HISTORY_MESSAGES: int = Field(default=12, ge=2, le=40)
    CHAT_MAX_PRODUCTS: int = Field(default=5, ge=1, le=10)
    CHAT_REQUESTS_PER_MINUTE: int = Field(default=15, ge=1, le=120)
    CHAT_GLOBAL_REQUESTS_PER_MINUTE: int = Field(default=120, ge=1, le=1000)
    CHAT_SESSIONS_PER_HOUR: int = Field(default=10, ge=1, le=100)
    CHAT_MAX_MESSAGES_PER_SESSION: int = Field(default=200, ge=1, le=1000)
    CHAT_PROCESSING_LEASE_SECONDS: int = Field(default=120, ge=60, le=600)
    CHAT_RETENTION_DAYS: int = Field(default=30, ge=1, le=365)
    STOREFRONT_URL: str = "https://darkdistrict.com.br/"
    LLM_PROVIDER: Literal["disabled", "openai_compatible"] = "disabled"
    LLM_MODEL: str = ""
    LLM_API_KEY: SecretStr = SecretStr("")
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_TIMEOUT_SECONDS: int = Field(default=20, ge=1, le=60)
    LLM_MAX_OUTPUT_TOKENS: int = Field(default=600, ge=100, le=2000)
    LLM_MAX_TOOL_CALLS: int = Field(default=4, ge=1, le=8)
    WHATSAPP_ENABLED: bool = False
    WHATSAPP_VERIFY_TOKEN: SecretStr = SecretStr("")
    META_APP_SECRET: SecretStr = SecretStr("")
    WHATSAPP_ACCESS_TOKEN: SecretStr = SecretStr("")
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_WABA_ID: str = ""
    WHATSAPP_GRAPH_VERSION: str = ""
    WHATSAPP_HTTP_TIMEOUT_SECONDS: int = Field(default=15, ge=1, le=60)
    DELIVERY_LEASE_SECONDS: int = Field(default=180, ge=120, le=900)
    DELIVERY_MAX_ATTEMPTS: int = Field(default=3, ge=1, le=10)
    WORKER_POLL_SECONDS: int = Field(default=2, ge=1, le=60)
    SHIPPING_ORIGIN_ADDRESS: str = "Chácara Patrícia, Estrada Roçado, S/N, Dom José Rodrigues, Juazeiro - BA"
    SHIPPING_ORIGIN_LATITUDE: float = Field(default=-9.4741012, ge=-90, le=90, allow_inf_nan=False)
    SHIPPING_ORIGIN_LONGITUDE: float = Field(default=-40.516211, ge=-180, le=180, allow_inf_nan=False)
    SHIPPING_GOOGLE_API_KEY: SecretStr = SecretStr("")
    SHIPPING_BASE_METERS: int = Field(default=1900, ge=0, le=100000)
    SHIPPING_BASE_CENTS: int = Field(default=600, ge=0, le=100000)
    SHIPPING_EXTRA_KM_CENTS: int = Field(default=150, ge=0, le=100000)
    SHIPPING_FREE_MIN_CENTS: int = Field(default=10000, gt=0, le=10000000)
    SHIPPING_FREE_RADIUS_METERS: int = Field(default=7000, ge=0, le=100000)
    SHIPPING_QUOTE_SECONDS: int = Field(default=600, ge=60, le=1800)
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

    @field_validator("LLM_BASE_URL", "STOREFRONT_URL")
    @classmethod
    def public_http_url(cls, value):
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Use uma URL HTTP(S) sem credenciais, query ou fragmento.")
        if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Use HTTPS para serviços externos.")
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
