from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProdutoImagemBase(BaseModel):
    url: str
    ordem: int = 0


class ProdutoImagemCreate(ProdutoImagemBase):
    pass


class ProdutoImagemResponse(ProdutoImagemBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class ProdutoVarianteBase(BaseModel):
    size: str | None = None
    color: str | None = None
    quantity: int = Field(default=0, ge=0)


class ProdutoVarianteCreate(ProdutoVarianteBase):
    pass


class ProdutoVarianteResponse(ProdutoVarianteBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class ProdutoCreate(BaseModel):
    id: str
    title: str
    description: str
    price: float = Field(ge=0)
    category: str
    gender: str
    available: bool = True
    featured: bool = False

    images: list[ProdutoImagemCreate] = []
    variants: list[ProdutoVarianteCreate] = []


class ProdutoUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    price: float | None = Field(default=None, ge=0)
    category: str | None = None
    gender: str | None = None
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