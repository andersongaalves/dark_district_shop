import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ShippingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True)

    @field_validator("*", mode="before")
    @classmethod
    def no_control_characters(cls, value):
        if isinstance(value, str) and re.search(r"[\x00-\x1f\x7f]", value):
            raise ValueError("Não use quebras de linha ou caracteres de controle.")
        return value


class DeliveryAddress(ShippingModel):
    recipient: str = Field(min_length=2, max_length=100)
    phone: str = Field(min_length=10, max_length=22)
    cep: str
    street: str = Field(min_length=3, max_length=150)
    number: str = Field(min_length=1, max_length=20)
    neighborhood: str = Field(min_length=2, max_length=100)
    city: str = Field(min_length=2, max_length=100)
    state: str = Field(pattern=r"^[A-Z]{2}$")
    complement: str = Field(default="", max_length=150)
    reference: str = Field(default="", max_length=200)

    @field_validator("cep")
    @classmethod
    def postal_code(cls, value):
        if not re.fullmatch(r"\d{5}-?\d{3}", value):
            raise ValueError("Informe um CEP com 8 dígitos.")
        return value.replace("-", "")

    @field_validator("phone")
    @classmethod
    def phone_number(cls, value):
        if not re.fullmatch(r"[+\d ()-]+", value):
            raise ValueError("Informe um telefone com DDD.")
        digits = re.sub(r"\D", "", value)
        if len(digits) in {12, 13} and digits.startswith("55"):
            digits = digits[2:]
        if len(digits) not in {10, 11}:
            raise ValueError("Informe um telefone com DDD.")
        return digits


class ShippingItem(ShippingModel):
    product_id: str = Field(min_length=1, max_length=50)
    variant_id: Annotated[int, Field(strict=True, gt=0)] | None = None
    quantity: int = Field(strict=True, ge=1, le=999)


class QuoteRequest(ShippingModel):
    address: DeliveryAddress
    items: list[ShippingItem] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_items(self):
        keys = [(item.product_id, item.variant_id) for item in self.items]
        if len(keys) != len(set(keys)):
            raise ValueError("Agrupe itens da mesma variante.")
        return self


class CheckoutRequest(QuoteRequest):
    quote_token: str = Field(min_length=1, max_length=2048)


class ShippingQuote(ShippingModel):
    quote_token: str
    expires_at: int
    subtotal_cents: int
    clothing_subtotal_cents: int
    shipping_cents: int
    total_cents: int
    radius_meters: int
    route_meters: int
    free_shipping: bool
    policy: str
