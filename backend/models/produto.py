from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Produto(Base):
    __tablename__ = "produtos"
    __table_args__ = (
        CheckConstraint("product_type IN ('catalogo', 'brecho', 'drop')", name="ck_produtos_product_type"),
        CheckConstraint("offer_price IS NULL OR (offer_price >= 0 AND offer_price < price)", name="ck_produtos_offer_price"),
    )

    product_type: Mapped[str] = mapped_column(String(20), default="catalogo", server_default="catalogo", nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categorias.id", ondelete="RESTRICT"), index=True, nullable=False)
    collection_id: Mapped[int | None] = mapped_column(ForeignKey("colecoes.id", ondelete="RESTRICT"), index=True, nullable=True)
    is_offer: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    offer_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    offer_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    category_record: Mapped["Category"] = relationship("Category")
    collection: Mapped["Collection | None"] = relationship("Collection")

    id: Mapped[str] = mapped_column(
        String(50),
        primary_key=True
    )

    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    price: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )

    # Compatibility label for published clients; category_id is the identity.
    category: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    gender: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    available: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )

    featured: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    images: Mapped[list["ProdutoImagem"]] = relationship(
        "ProdutoImagem",
        back_populates="produto",
        cascade="all, delete-orphan",
        order_by="ProdutoImagem.ordem, ProdutoImagem.id"
    )

    variants: Mapped[list["ProdutoVariante"]] = relationship(
        "ProdutoVariante",
        back_populates="produto",
        cascade="all, delete-orphan"
    )

    @property
    def offer_active(self) -> bool:
        end = self.offer_ends_at
        # SQLite used in tests returns naive datetimes; stored values are UTC.
        if end is not None and end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return bool(self.is_offer and (end is None or end > datetime.now(timezone.utc)))

    @property
    def effective_price(self) -> float:
        return self.offer_price if self.offer_active and self.offer_price is not None else self.price


class ProdutoImagem(Base):
    __tablename__ = "produto_imagens"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    produto_id: Mapped[str] = mapped_column(
        ForeignKey("produtos.id", ondelete="CASCADE"),
        nullable=False
    )

    url: Mapped[str] = mapped_column(
        String(500),
        nullable=False
    )

    ordem: Mapped[int] = mapped_column(
        default=0,
        nullable=False
    )

    produto: Mapped["Produto"] = relationship(
        "Produto",
        back_populates="images"
    )


class ProdutoVariante(Base):
    __tablename__ = "produto_variantes"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    produto_id: Mapped[str] = mapped_column(
        ForeignKey("produtos.id", ondelete="CASCADE"),
        nullable=False
    )

    size: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True
    )

    color: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )

    quantity: Mapped[int] = mapped_column(
        default=0,
        nullable=False
    )

    produto: Mapped["Produto"] = relationship(
        "Produto",
        back_populates="variants"
    )
