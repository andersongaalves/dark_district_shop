from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from core.security import get_current_user
from database import get_db
from models.produto import Produto
from schemas.produto import ProdutoCreate, ProdutoResponse, ProdutoUpdate, ProductType
from services import produtos as service


router = APIRouter(prefix="/produtos", tags=["Produtos"])
protected = [Depends(get_current_user)]


@router.get("", response_model=list[ProdutoResponse])
def listar_produtos(db: Session = Depends(get_db), product_type: ProductType | None = None,
                    category_id: int | None = Query(default=None, gt=0, le=2_147_483_647),
                    collection_id: int | None = Query(default=None, gt=0, le=2_147_483_647),
                    featured: bool | None = None, is_offer: bool | None = None,
                    available: bool | None = None):
    return service.listar_produtos(db, product_type=product_type, category_id=category_id,
                                  collection_id=collection_id, featured=featured,
                                  is_offer=is_offer, available=available)


@router.get("/{produto_id}", response_model=ProdutoResponse)
def obter_produto(produto_id: str, db: Session = Depends(get_db)):
    produto = service.obter_produto(db, produto_id)
    if produto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Produto não encontrado.")
    return produto


@router.post("", response_model=ProdutoResponse,
             status_code=status.HTTP_201_CREATED, dependencies=protected)
def criar_produto(dados: ProdutoCreate, db: Session = Depends(get_db)):
    try:
        return service.criar_produto(db, dados)
    except service.ProdutoDuplicadoError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Já existe um produto com este ID."
        ) from None


@router.put("/{produto_id}", response_model=ProdutoResponse, dependencies=protected)
def atualizar_produto(dados: ProdutoUpdate,
                      produto: Produto = Depends(obter_produto),
                      db: Session = Depends(get_db)):
    return service.atualizar_produto(db, produto, dados)


@router.delete("/{produto_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=protected)
def excluir_produto(produto: Produto = Depends(obter_produto),
                    db: Session = Depends(get_db)):
    service.excluir_produto(db, produto)


@router.patch("/{produto_id}/vendido", response_model=ProdutoResponse,
              dependencies=protected)
def marcar_produto_vendido(produto: Produto = Depends(obter_produto),
                           db: Session = Depends(get_db)):
    return service.marcar_produto_vendido(db, produto)
