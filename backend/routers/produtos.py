from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.security import get_current_user
from database import get_db
from models.produto import Produto, ProdutoImagem, ProdutoVariante
from models.usuario import Usuario
from schemas.produto import (
    ProdutoCreate,
    ProdutoResponse,
    ProdutoUpdate,
)


router = APIRouter(
    prefix="/produtos",
    tags=["Produtos"]
)


@router.get(
    "",
    response_model=list[ProdutoResponse]
)
def listar_produtos(
    db: Session = Depends(get_db)
):
    return db.query(Produto).all()


@router.get(
    "/{produto_id}",
    response_model=ProdutoResponse
)
def obter_produto(
    produto_id: str,
    db: Session = Depends(get_db)
):
    produto = (
        db.query(Produto)
        .filter(Produto.id == produto_id)
        .first()
    )

    if not produto:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto não encontrado."
        )

    return produto


@router.post(
    "",
    response_model=ProdutoResponse,
    status_code=status.HTTP_201_CREATED
)
def criar_produto(
    dados: ProdutoCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user)
):
    produto_existente = (
        db.query(Produto)
        .filter(Produto.id == dados.id)
        .first()
    )

    if produto_existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um produto com este ID."
        )

    produto = Produto(
        id=dados.id,
        title=dados.title,
        description=dados.description,
        price=dados.price,
        category=dados.category,
        gender=dados.gender,
        available=dados.available,
        featured=dados.featured,
    )

    for imagem in dados.images:
        produto.images.append(
            ProdutoImagem(
                url=imagem.url,
                ordem=imagem.ordem
            )
        )

    for variante in dados.variants:
        produto.variants.append(
            ProdutoVariante(
                size=variante.size,
                color=variante.color,
                quantity=variante.quantity
            )
        )

    db.add(produto)
    db.commit()
    db.refresh(produto)

    return produto


@router.put(
    "/{produto_id}",
    response_model=ProdutoResponse
)
def atualizar_produto(
    produto_id: str,
    dados: ProdutoUpdate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user)
):
    produto = (
        db.query(Produto)
        .filter(Produto.id == produto_id)
        .first()
    )

    if not produto:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto não encontrado."
        )

    campos = [
        "title",
        "description",
        "price",
        "category",
        "gender",
        "available",
        "featured",
    ]

    for campo in campos:
        valor = getattr(dados, campo)

        if valor is not None:
            setattr(produto, campo, valor)

    if dados.images is not None:
        produto.images.clear()

        for imagem in dados.images:
            produto.images.append(
                ProdutoImagem(
                    url=imagem.url,
                    ordem=imagem.ordem
                )
            )

    if dados.variants is not None:
        produto.variants.clear()

        for variante in dados.variants:
            produto.variants.append(
                ProdutoVariante(
                    size=variante.size,
                    color=variante.color,
                    quantity=variante.quantity
                )
            )

    db.commit()
    db.refresh(produto)

    return produto


@router.delete(
    "/{produto_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def excluir_produto(
    produto_id: str,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user)
):
    produto = (
        db.query(Produto)
        .filter(Produto.id == produto_id)
        .first()
    )

    if not produto:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto não encontrado."
        )

    db.delete(produto)
    db.commit()


@router.patch(
    "/{produto_id}/vendido",
    response_model=ProdutoResponse
)
def marcar_produto_vendido(
    produto_id: str,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user)
):
    produto = (
        db.query(Produto)
        .filter(Produto.id == produto_id)
        .first()
    )

    if not produto:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto não encontrado."
        )

    produto.available = False

    db.commit()
    db.refresh(produto)

    return produto