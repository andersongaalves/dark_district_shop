from secrets import token_hex

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from models.produto import Produto, ProdutoImagem, ProdutoVariante
from models.catalog import Category, Collection
from schemas.produto import ProdutoCreate, ProdutoUpdate
from services.catalog import CatalogError, resolve_reference


class ProdutoDuplicadoError(Exception):
    pass


def listar_produtos(db: Session, **filters) -> list[Produto]:
    query = db.query(Produto).options(
        selectinload(Produto.images), selectinload(Produto.variants)
    )
    for field in ("product_type", "category_id", "collection_id", "featured", "is_offer", "available"):
        if filters.get(field) is not None:
            query = query.filter(getattr(Produto, field) == filters[field])
    return query.order_by(Produto.created_at.desc(), Produto.id).all()


def obter_produto(db: Session, produto_id: str) -> Produto | None:
    return db.get(Produto, produto_id)


def _aplicar_categoria(db: Session, produto: Produto, dados):
    category = None
    if dados.category_id is not None:
        category = resolve_reference(db, Category, dados.category_id, produto.category_id)
        if dados.category is not None and dados.category != category.name:
            raise CatalogError("category e category_id não correspondem à mesma categoria.")
    elif "category_id" in dados.model_fields_set:
        raise CatalogError("A categoria do produto é obrigatória.")
    elif dados.category is not None:
        # Transitional support for the already published text-based write contract.
        # All such writes still create/resolve a real entity; the new ADM sends IDs.
        category = db.scalar(select(Category).where(Category.name == dados.category).with_for_update())
        if category is None:
            category = Category(name=dados.category, slug=f"legacy-{token_hex(12)}", active=True)
            db.add(category)
            db.flush()
        elif not category.active and category.id != produto.category_id:
            raise CatalogError("Categoria desativada. Selecione uma opção ativa.")
    if category is not None:
        produto.category_record = category
        produto.category_id = category.id
        produto.category = category.name


def _aplicar_variantes(produto: Produto, variants):
    existing = {variant.id: variant for variant in produto.variants}
    result, used, combinations = [], set(), set()
    for data in variants:
        combination = (data.size or None, data.color or None)
        if combination in combinations:
            raise CatalogError("Há variantes repetidas com o mesmo tamanho e cor.")
        combinations.add(combination)
        if data.id is not None:
            variant = existing.get(data.id)
            if variant is None or data.id in used:
                raise CatalogError("ID de variante inválido ou não pertencente a este produto.")
        else:
            matches = [item for item in existing.values()
                       if item.id not in used and (item.size or None, item.color or None) == combination]
            variant = matches[0] if len(matches) == 1 else ProdutoVariante()
        if variant.id is not None:
            if variant.id in used:
                raise CatalogError("ID de variante repetido.")
            used.add(variant.id)
        for field, value in data.model_dump(exclude={"id"}).items():
            setattr(variant, field, value)
        result.append(variant)
    produto.variants = result


def _aplicar_dados(db: Session, produto: Produto, dados: ProdutoCreate | ProdutoUpdate) -> None:
    _aplicar_categoria(db, produto, dados)
    if "collection_id" in dados.model_fields_set:
        collection = None if dados.collection_id is None else resolve_reference(
            db, Collection, dados.collection_id, produto.collection_id
        )
        produto.collection = collection
        produto.collection_id = collection.id if collection else None
    # Preserve partial PUT semantics: omitted/null fields leave existing values intact.
    # collection_id is the explicit exception: null clears the optional reference.
    campos = dados.model_dump(exclude={"images", "variants", "category", "category_id", "collection_id"}, exclude_none=True)
    for campo, valor in campos.items():
        setattr(produto, campo, valor)
    if dados.images is not None:
        produto.images = [ProdutoImagem(**imagem.model_dump()) for imagem in dados.images]
    if dados.variants is not None:
        _aplicar_variantes(produto, dados.variants)


def _commit(db: Session) -> None:
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


def criar_produto(db: Session, dados: ProdutoCreate) -> Produto:
    if obter_produto(db, dados.id) is not None:
        raise ProdutoDuplicadoError
    produto = Produto()
    try:
        _aplicar_dados(db, produto, dados)
        db.add(produto)
        _commit(db)
    except IntegrityError:
        db.rollback()
        # A concurrent request may have inserted the same ID after our first lookup.
        if obter_produto(db, dados.id) is not None:
            raise ProdutoDuplicadoError from None
        raise CatalogError("Conflito nos dados do produto. Atualize e tente novamente.", 409) from None
    except CatalogError:
        db.rollback()
        raise
    db.refresh(produto)
    return produto


def atualizar_produto(db: Session, produto: Produto, dados: ProdutoUpdate) -> Produto:
    try:
        _aplicar_dados(db, produto, dados)
        _commit(db)
    except (CatalogError, IntegrityError) as error:
        db.rollback()
        if isinstance(error, CatalogError):
            raise
        raise CatalogError("Conflito nos vínculos do produto. Atualize e tente novamente.", 409) from None
    db.refresh(produto)
    return produto


def excluir_produto(db: Session, produto: Produto) -> None:
    db.delete(produto)
    _commit(db)


def marcar_produto_vendido(db: Session, produto: Produto) -> Produto:
    return atualizar_produto(db, produto, ProdutoUpdate(available=False))
