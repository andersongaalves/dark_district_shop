from datetime import datetime, timezone
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

ProductType = Literal["catalogo", "brecho", "drop"]


class ProdutoImagemBase(BaseModel):
    url: str = Field(max_length=500)
    ordem: int = Field(default=0, ge=-2_147_483_648, le=2_147_483_647)


class ProdutoImagemCreate(ProdutoImagemBase):
    pass


class ProdutoImagemResponse(ProdutoImagemBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class ProdutoVarianteBase(BaseModel):
    size: str | None = Field(default=None, max_length=50)
    color: str | None = Field(default=None, max_length=100)
    quantity: int = Field(default=0, ge=0, le=2_147_483_647)


class ProdutoVarianteCreate(ProdutoVarianteBase):
    id: int | None = Field(default=None, gt=0, le=2_147_483_647)


class ProdutoVarianteResponse(ProdutoVarianteBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class ProdutoOfferFields(BaseModel):
    offer_price: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    offer_ends_at: AwareDatetime | None = None

    @field_validator("offer_ends_at")
    @classmethod
    def normalize_offer_timezone(cls, value):
        return value.astimezone(timezone.utc) if value is not None else None


class ProdutoCreate(ProdutoOfferFields):
    id: str = Field(min_length=1, max_length=50, pattern=r"^[^/\\\x00-\x1f\x7f]+$")
    title: str = Field(max_length=200)
    description: str
    price: float = Field(ge=0, allow_inf_nan=False)
    category: str | None = Field(default=None, max_length=100, json_schema_extra={"deprecated": True})
    category_id: int | None = Field(default=None, gt=0, le=2_147_483_647)
    collection_id: int | None = Field(default=None, gt=0, le=2_147_483_647)
    product_type: ProductType = "catalogo"
    is_offer: bool = False
    gender: str = Field(max_length=50)
    available: bool = True
    featured: bool = False

    images: list[ProdutoImagemCreate] = Field(default_factory=list)
    variants: list[ProdutoVarianteCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_category(self):
        if self.category_id is None and self.category is None:
            raise ValueError("Informe category_id.")
        return self


class ProdutoUpdate(ProdutoOfferFields):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = None
    price: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    category: str | None = Field(default=None, max_length=100, json_schema_extra={"deprecated": True})
    category_id: int | None = Field(default=None, gt=0, le=2_147_483_647)
    collection_id: int | None = Field(default=None, gt=0, le=2_147_483_647)
    product_type: ProductType | None = None
    is_offer: bool | None = None
    gender: str | None = Field(default=None, max_length=50)
    available: bool | None = None
    featured: bool | None = None

    images: list[ProdutoImagemCreate] | None = None
    variants: list[ProdutoVarianteCreate] | None = None


class ProdutoResponse(BaseModel):
    id: str
    title: str
    description: str
    price: float
    category: str
    category_id: int
    collection_id: int | None
    product_type: ProductType
    is_offer: bool
    offer_price: float | None
    offer_ends_at: datetime | None
    offer_active: bool
    effective_price: float
    gender: str
    available: bool
    featured: bool
    created_at: datetime
    updated_at: datetime

    images: list[ProdutoImagemResponse]
    variants: list[ProdutoVarianteResponse]

    model_config = ConfigDict(from_attributes=True)

    @field_validator("offer_ends_at")
    @classmethod
    def serialize_offer_timezone(cls, value):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
