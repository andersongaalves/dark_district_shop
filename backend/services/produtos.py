from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from models.produto import Produto, ProdutoImagem, ProdutoVariante
from schemas.produto import ProdutoCreate, ProdutoUpdate


class ProdutoDuplicadoError(Exception):
    pass


def listar_produtos(db: Session) -> list[Produto]:
    return db.query(Produto).options(
        selectinload(Produto.images), selectinload(Produto.variants)
    ).all()


def obter_produto(db: Session, produto_id: str) -> Produto | None:
    return db.get(Produto, produto_id)


def _aplicar_dados(produto: Produto, dados: ProdutoCreate | ProdutoUpdate) -> None:
    # Preserve partial PUT semantics: omitted/null fields leave existing values intact.
    campos = dados.model_dump(exclude={"images", "variants"}, exclude_none=True)
    for campo, valor in campos.items():
        setattr(produto, campo, valor)
    if dados.images is not None:
        produto.images = [ProdutoImagem(**imagem.model_dump()) for imagem in dados.images]
    if dados.variants is not None:
        produto.variants = [ProdutoVariante(**variante.model_dump()) for variante in dados.variants]


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
    _aplicar_dados(produto, dados)
    db.add(produto)
    try:
        _commit(db)
    except IntegrityError:
        # A concurrent request may have inserted the same ID after our first lookup.
        if obter_produto(db, dados.id) is not None:
            raise ProdutoDuplicadoError from None
        raise
    db.refresh(produto)
    return produto


def atualizar_produto(db: Session, produto: Produto, dados: ProdutoUpdate) -> Produto:
    _aplicar_dados(produto, dados)
    _commit(db)
    db.refresh(produto)
    return produto


def excluir_produto(db: Session, produto: Produto) -> None:
    db.delete(produto)
    _commit(db)


def marcar_produto_vendido(db: Session, produto: Produto) -> Produto:
    return atualizar_produto(db, produto, ProdutoUpdate(available=False))
