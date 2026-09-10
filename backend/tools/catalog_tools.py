"""Catalog tools reuse the store services and return current database facts."""

from dataclasses import dataclass, field
from typing import Annotated, Literal
from urllib.parse import quote, urljoin

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from core.config import settings
from schemas.atendimento import ChatProduct
from schemas.produto import Garment, ProdutoResponse
from schemas.faq import FAQItem
from services.produtos import listar_produtos, obter_produto


ShortText = Annotated[str, Field(min_length=1, max_length=100)]
ProductId = Annotated[str, Field(min_length=1, max_length=50)]


class ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class SearchArguments(ToolArguments):
    query: ShortText | None = None
    garment: Garment | None = None
    category: ShortText | None = None
    size: Annotated[str, Field(min_length=1, max_length=50)] | None = None
    color: ShortText | None = None
    max_price: Annotated[float, Field(ge=0, le=1_000_000, allow_inf_nan=False)] | None = None
    product_type: Literal["catalogo", "brecho", "drop"] | None = None
    offer_active: bool | None = None
    product_id: ProductId | None = None
    limit: Annotated[int, Field(ge=1, le=10)] = 5


class CategoryArguments(SearchArguments):
    category: ShortText


class SizeArguments(SearchArguments):
    size: Annotated[str, Field(min_length=1, max_length=50)]


class ColorArguments(SearchArguments):
    color: ShortText


class ProductArguments(ToolArguments):
    product_id: ProductId


class StockArguments(ProductArguments):
    size: Annotated[str, Field(min_length=1, max_length=50)] | None = None
    color: ShortText | None = None


@dataclass
class ToolResult:
    products: list[ChatProduct] = field(default_factory=list)
    filters: dict = field(default_factory=dict)
    error: str | None = None
    faqs: list[FAQItem] = field(default_factory=list)


def serialize_product(product) -> ChatProduct:
    # Product IDs are opaque strings in the existing catalog, never LLM URLs.
    product_url = urljoin(str(settings.STOREFRONT_URL).rstrip("/") + "/", "pages/produto/index.html")
    data = ChatProduct.model_validate({
        **ProdutoResponse.model_validate(product).model_dump(),
        "url": f"{product_url}?id={quote(product.id, safe='')}",
    })
    return data


def search(db: Session, arguments: SearchArguments) -> ToolResult:
    values = arguments.model_dump(exclude_none=True)
    filters = {key: value for key, value in values.items() if key != "limit"}
    products = listar_produtos(
        db,
        query=arguments.query,
        garment=arguments.garment,
        category_name=arguments.category,
        size=arguments.size,
        color=arguments.color,
        max_price=arguments.max_price,
        product_type=arguments.product_type,
        offer_active=arguments.offer_active,
        product_ids=[arguments.product_id] if arguments.product_id else None,
        in_stock=True,
        limit=min(arguments.limit, settings.CHAT_MAX_PRODUCTS),
    )
    return ToolResult(products=[serialize_product(product) for product in products], filters=filters)


def lookup(db: Session, arguments: ProductArguments) -> ToolResult:
    product = obter_produto(db, arguments.product_id)
    return ToolResult(
        products=[serialize_product(product)] if product is not None else [],
        filters=arguments.model_dump(exclude_none=True),
    )
