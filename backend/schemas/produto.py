from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
    pass


class ProdutoVarianteResponse(ProdutoVarianteBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class ProdutoCreate(BaseModel):
    id: str = Field(max_length=50)
    title: str = Field(max_length=200)
    description: str
    price: float = Field(ge=0, allow_inf_nan=False)
    category: str = Field(max_length=100)
    gender: str = Field(max_length=50)
    available: bool = True
    featured: bool = False

    images: list[ProdutoImagemCreate] = Field(default_factory=list)
    variants: list[ProdutoVarianteCreate] = Field(default_factory=list)


class ProdutoUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = None
    price: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    category: str | None = Field(default=None, max_length=100)
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
    gender: str
    available: bool
    featured: bool
    created_at: datetime
    updated_at: datetime

    images: list[ProdutoImagemResponse]
    variants: list[ProdutoVarianteResponse]

    model_config = ConfigDict(from_attributes=True)
